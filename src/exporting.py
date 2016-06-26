import bmesh
import bpy
import bpy_extras
import math
from mathutils import Matrix, Vector
from .binary_io import BinaryWriter
from .kcl_file import KclModel

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

    max_octree_cube_triangles = bpy.props.IntProperty(
        name="Max. Cube Triangles",
        description="The maximum amount of triangles in a spatial cube before it is attempted to split it.",
        default=30
    )
    min_octree_cube_size = bpy.props.IntProperty(
        name="Min. Cube Size",
        description="The minimum size of a spatial cube into which triangles will be sorted.",
        default=256
    )

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
        collision_layer = bm.faces.layers.int["collision_flags"]
        # Compute the minimum and maximum point of the bounding box with additional padding taken from Gu_Menu.
        bb_min = [None] * 3
        bb_max = [None] * 3
        for vert in bm.verts:
            for i in range(0, 3):
                if bb_min[i] is None or vert.co[i] < bb_min[i]: bb_min[i] = vert.co[i]
                if bb_max[i] is None or vert.co[i] > bb_max[i]: bb_max[i] = vert.co[i]
        bb_min = Vector((bb_min[0] - 50, bb_min[1] - 80, bb_min[2] - 50))
        bb_max = Vector((bb_max[0] + 50, bb_max[1] + 50, bb_max[2] + 50))
        # Compute the shift and the required number of divisions.
        n_min = self._next_exponent(self.operator.min_octree_cube_size)
        n_x = max(self._next_exponent(bb_max.x - bb_min.x), n_min)
        n_y = max(self._next_exponent(bb_max.y - bb_min.y), n_min)
        n_z = max(self._next_exponent(bb_max.z - bb_min.z), n_min)
        n = max(min(n_x, n_y, n_z) - 1, n_min)
        divs_x = 2 ** (n_x - n)
        divs_y = 2 ** (n_y - n)
        divs_z = 2 ** (n_z - n)
        width = 2 ** n
        # Build the octree.
        octree = [KclModel.OctreeNode(bb_min + width * Vector((x, y, z)),
                                      width, bm, range(0, len(bm.faces)),
                                      self.operator.max_octree_cube_triangles,
                                      self.operator.min_octree_cube_size)
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
            writer.write_uint32(n_x) # Coordinate shift X
            writer.write_uint32(n_y) # Coordinate shift Y
            writer.write_uint32(n_z) # Coordinate shift Z
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
                writer.write_single((0xFFFFFFFF << n_x) & 0xFFFFFFFF) # Mask X
                writer.write_single((0xFFFFFFFF << n_y) & 0xFFFFFFFF) # Mask Y
                writer.write_single((0xFFFFFFFF << n_z) & 0xFFFFFFFF) # Mask Z
                writer.write_uint32(n) # Coordinate Shift X
                writer.write_uint32(n_x - n) # Coordinate Shift Y
                writer.write_uint32(n_x - n + n_y - n) # Coordinate Shift Z
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
                    n = face.normal
                    a = -((w - u).cross(n)).normalized()
                    b = (v - u).cross(n).normalized()
                    c = (w - v).cross(n).normalized()
                    writer.write_singles(n)
                    writer.write_singles(a)
                    writer.write_singles(b)
                    writer.write_singles(c)
                # Write the triangles section.
                writer.satisfy_offset(triangles_offset, writer.tell() - model_address)
                for j, face in enumerate(bm.faces):
                    u = face.verts[0].co
                    v = face.verts[1].co
                    w = face.verts[2].co
                    n = face.normal
                    c = (w - v).cross(n).normalized()
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
        return {"FINISHED"}

    @staticmethod
    def _next_exponent(value):
        # Return the lowest integer n so that value <= 2 ** n.
        if value <= 1:
            return 0
        return int(math.ceil(math.log(value, 2)))

