import bmesh
import bpy
import bpy_extras
import math
import os
from mathutils import Matrix, Vector
from .binary_io import BinaryWriter
from .kcl_file import KclFile, KclModel

class ExportOperator(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
    bl_idname = "export_scene.kcl"
    bl_label = "Export KCL"

    filename_ext = ".kcl"
    filter_glob = bpy.props.StringProperty(
        default="*.kcl",
        options={"HIDDEN"}
    )
    filepath = bpy.props.StringProperty(
        name="File Path",
        description="Filepath used for exporting the KCL file",
        maxlen=1024,
        default=""
    )
    check_extension = True

    write_new_model = bpy.props.BoolProperty(
        name="[Experimental] Write new Model",
        description="The model and octree will be rewritten instead of just replacing the collision flags.",
        default=False
    )
    max_octree_cube_triangles = bpy.props.IntProperty(
        name="Max. Cube Triangles",
        description="The maximum amount of triangles in a spatial cube before it is attempted to split it.",
        default=32
    )
    min_octree_cube_size = bpy.props.IntProperty(
        name="Min. Cube Size",
        description="The minimum size of a spatial cube into which triangles will be sorted.",
        default=256
    )

    def draw(self, context):
        layout = self.layout
        # Write New Model
        layout.prop(self, "write_new_model")
        # Max. Cube Triangles
        row = layout.row()
        row.enabled = self.write_new_model
        row.prop(self, "max_octree_cube_triangles")
        # Min. Cube Size
        row = layout.row()
        row.enabled = self.write_new_model
        row.prop(self, "min_octree_cube_size")
        # Warning label
        if self.write_new_model:
            self.layout.row().label("This does not work in-game yet.", icon="ERROR")

    @staticmethod
    def menu_func_export(self, context):
        self.layout.operator(ExportOperator.bl_idname, text="Nintendo KCL (.kcl)")

    def execute(self, context):
        exporter = Exporter(self, context, self.properties.filepath)
        return exporter.run()

class Exporter:
    def __init__(self, operator, context, filepath):
        self.operator = operator
        self.context = context
        self.filepath = filepath

    def run(self):
        if self.operator.write_new_model:
            self._create_new_model()
        else:
            self._update_collision_flags()
        return {"FINISHED"}

    def _create_new_model(self):
        # Prepare the list of models to export (e.g., every object which is a mesh).
        parent_obj = self.context.scene.objects.get("KCL")
        if parent_obj is None:
            raise AssertionError("No KCL parent object found. Children must be parented to an empty KCL object.")
        mesh_objects = []
        for obj in parent_obj.children:
            if obj.type == "MESH":
                mesh_objects.append(obj)
        if len(mesh_objects) == 0:
            raise AssertionError("No KCL models found. They must be children to the existing, empty KCL parent object.")
        # TODO: We only support 1 model at the moment, so they get merged into one.
        # TODO: They should at least be converted to global space before joining in case they are offset.
        bm = bmesh.new()
        for mesh_object in mesh_objects:
            bm.from_mesh(mesh_object.data)
        # Transform the coordinate system so that Y is up.
        matrix_z_to_y = Matrix(((1, 0, 0), (0, 0, 1), (0, -1, 0)))
        bmesh.ops.transform(bm, matrix=matrix_z_to_y, verts=bm.verts)
        bm.faces.ensure_lookup_table()
        collision_layer = bm.faces.layers.int["kcl_flags"]
        # Find the minimum and maximum point of the model.
        bb_min = [None] * 3
        bb_max = [None] * 3
        for vert in bm.verts:
            for i in range(0, 3):
                if bb_min[i] is None or vert.co[i] < bb_min[i]: bb_min[i] = vert.co[i]
                if bb_max[i] is None or vert.co[i] > bb_max[i]: bb_max[i] = vert.co[i]
        # Find the exponents with which the world size (the cuboid which includes all sub cubes) is calculated.
        exponents = (self._next_power_of_2(bb_max[0] - bb_min[0]),
                     self._next_power_of_2(bb_max[1] - bb_min[1]),
                     self._next_power_of_2(bb_max[2] - bb_min[2]))
        # Find the size of the sub cubes which must be powers of 2 (unlike the cuboid world holding them).
        sub_cube_exponent = min(exponents) - 1
        divs_x = 2 ** (exponents[0] - sub_cube_exponent)
        divs_y = 2 ** (exponents[1] - sub_cube_exponent)
        divs_z = 2 ** (exponents[2] - sub_cube_exponent)
        cube_size = 2 ** sub_cube_exponent
        # Build the octree, creating the first level of sub cubes.
        octree = [KclModel.OctreeNode(Vector(bb_min) + (Vector((x, y, z)) * cube_size), cube_size,
            bm, range(0, len(bm.faces)),
            self.operator.max_octree_cube_triangles, self.operator.min_octree_cube_size)
            for z in range(0, divs_z) for y in range(0, divs_y) for x in range(0, divs_x)]
        # Write the KCL file.
        with BinaryWriter(open(self.filepath, "wb")) as writer:
            writer.endianness = ">"
            # Write the header.
            writer.write_uint32(0x02020000) # Header bytes
            model_octree_offset = writer.reserve_offset()
            model_offset_array_offset = writer.reserve_offset()
            writer.write_uint32(1) # Model count
            writer.write_singles(bb_min)
            writer.write_singles(bb_max)
            writer.write_uint32(exponents[0]) # Coordinate shift X
            writer.write_uint32(exponents[1]) # Coordinate shift Y
            writer.write_uint32(exponents[2]) # Coordinate shift Z
            writer.write_uint32(0) # unknown0x34, seems to be stable with 0.
            # Write the model octree. TODO: This is a dummy octree just supporting one model at the moment.
            writer.satisfy_offset(model_octree_offset, writer.tell())
            writer.write_uint32s([0x80000000] * 8)
            # Write the model offset array.
            writer.satisfy_offset(model_offset_array_offset, writer.tell())
            mesh_offsets = []
            for i in range(0, 1): # Only 1 model at the moment
                mesh_offsets.append(writer.reserve_offset())
            # Write the model section (which has offsets relative to itself, as it's just modified MKWii KCL data).
            for i in range(0, 1): # Only 1 model at the moment
                model_address = writer.tell()
                writer.satisfy_offset(mesh_offsets[i], model_address)
                # Write the model header.
                positions_offset = writer.reserve_offset()
                normals_offset = writer.reserve_offset()
                triangles_offset = writer.reserve_offset()
                octree_offset = writer.reserve_offset()
                writer.write_single(30) # unknown0x10
                writer.write_singles(bb_min)
                writer.write_single((0xFFFFFFFF << exponents[0]) & 0xFFFFFFFF) # Mask X
                writer.write_single((0xFFFFFFFF << exponents[1]) & 0xFFFFFFFF) # Mask Y
                writer.write_single((0xFFFFFFFF << exponents[2]) & 0xFFFFFFFF) # Mask Z
                writer.write_uint32(sub_cube_exponent) # Coordinate Shift X
                writer.write_uint32(exponents[0] - sub_cube_exponent) # Coordinate Shift Y
                writer.write_uint32(exponents[0] - sub_cube_exponent + exponents[1] - sub_cube_exponent) # Coordinate Shift Z
                writer.write_single(0) # unknown0x38
                # Write the positions section.
                writer.satisfy_offset(positions_offset, writer.tell() - model_address)
                for face in bm.faces:
                    writer.write_singles(face.verts[0].co)
                # Write the normals section.
                writer.satisfy_offset(normals_offset, writer.tell() - model_address)
                for face in bm.faces:
                    u = face.verts[0].co
                    v = face.verts[1].co
                    w = face.verts[2].co
                    sub_cube_exponent = face.normal
                    a = -((w - u).cross(sub_cube_exponent)).normalized()
                    b = (v - u).cross(sub_cube_exponent).normalized()
                    c = (w - v).cross(sub_cube_exponent).normalized()
                    writer.write_singles(sub_cube_exponent)
                    writer.write_singles(a)
                    writer.write_singles(b)
                    writer.write_singles(c)
                # Write the triangles section.
                writer.satisfy_offset(triangles_offset, writer.tell() - model_address)
                for j, face in enumerate(bm.faces):
                    u = face.verts[0].co
                    v = face.verts[1].co
                    w = face.verts[2].co
                    sub_cube_exponent = face.normal
                    c = (w - v).cross(sub_cube_exponent).normalized()
                    writer.write_single((w - u).dot(c)) # Length
                    writer.write_uint16(j) # Position index
                    writer.write_uint16(4 * j) # Direction index
                    writer.write_uint16(4 * j + 1) # Normal A index
                    writer.write_uint16(4 * j + 2) # Normal B index
                    writer.write_uint16(4 * j + 3) # Normal C index
                    writer.write_uint16(face[collision_layer]) # Collision flags
                    writer.write_uint32(j) # Global triangle index TODO: Has to change for multiple models.
                # Write the octree section.
                octree_address = writer.tell()
                writer.satisfy_offset(octree_offset, octree_address - model_address)
                writer.write_uint32s([0x00000000] * len(octree)) # Space for nodes to offset the triangle indices.
                writer.seek(octree_address)
                for node in octree:
                    node.write(writer, octree_address)
        bm.free()

    @staticmethod
    def _next_power_of_2(value):
        # Return the next power of 2 bigger than the value.
        if value <= 1:
            return 0
        return int(math.ceil(math.log(value, 2)))

    def _update_collision_flags(self):
        # This only works when overwriting an existing file, since information is required from it.
        if not os.path.isfile(self.filepath):
            raise AssertionError("Please select an existing file to modify if you are not exporting a new model.")
        # Ensure we left edit mode, so that the bmesh data of a mesh in edit mode is written back.
        if self.context.active_object.mode == "EDIT":
            bpy.ops.object.mode_set(mode="OBJECT")
        # Prepare the list of models which have to be iterated.
        parent_obj = self.context.scene.objects.get("KCL")
        if parent_obj is None:
            raise AssertionError("No KCL parent object found. Children must be parented to an empty KCL object.")
        models = []
        for obj in parent_obj.children:
            if obj.type == "MESH":
                models.append(obj.data)
        if len(models) == 0:
            raise AssertionError("No KCL models found. They must be children to the existing, empty KCL parent object.")
        # Load them into one bmesh instance to traverse its faces.
        bm = bmesh.new()
        for model in models:
            bm.from_mesh(model)
        model_index_layer = bm.faces.layers.int["kcl_model_index"]
        face_index_layer = bm.faces.layers.int["kcl_face_index"]
        flags_layer = bm.faces.layers.int["kcl_flags"]
        # Load the existing file into memory and open it for overwriting parts.
        kcl_file = KclFile(open(self.filepath, "rb"))
        with BinaryWriter(open(self.filepath, "r+b")) as writer:
            writer.endianness = ">"
            # Iterate through the faces.
            for face in bm.faces:
                model_index = face[model_index_layer]
                face_index = face[face_index_layer]
                flags = face[flags_layer]
                # Find the offset in the file and write the new collision flags to it.
                kcl_model = kcl_file.models[model_index]
                offset = kcl_model.header.triangles_offset + (0x14 * face_index) + 0x0E
                writer.seek(offset)
                writer.write_uint16(flags)
        bm.free()
