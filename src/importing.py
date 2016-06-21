import bmesh
import bpy
import bpy_extras
import os
from .log import Log
from .kcl_file import KclFile

class ImportOperator(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
    bl_idname = "import_scene.kcl"
    bl_label = "Import KCL"
    bl_options = {"UNDO"}

    filename_ext = ".kcl"
    filter_glob = bpy.props.StringProperty(
        default="*.kcl",
        options={"HIDDEN"}
    )
    filepath = bpy.props.StringProperty(
        name="File Path",
        description="Filepath used for importing the KCL file",
        maxlen=1024,
        default=""
    )

    def execute(self, context):
        importer = Importer(self, context, self.properties.filepath)
        return importer.run()

    @staticmethod
    def menu_func_import(self, context):
        self.layout.operator(ImportOperator.bl_idname, text="Nintendo KCL (.kcl)")

class MarioKart8EditPanel(bpy.types.Panel):
    bl_context = "EDITMODE"
    bl_label = "Mario Kart 8"
    bl_region_type = "UI"
    bl_space_type = "VIEW_3D"

    @classmethod
    def poll(cls, context):
        # Only allow in edit mode for a selected mesh.
        return context.mode == "EDIT_MESH" and context.object is not None and context.object.type == "MESH"

    def draw(self, context):
        obj = context.object
        bm = bmesh.from_edit_mesh(obj.data)
        face = bm.faces.active
        collision_flag_layer = bm.faces.layers.int.get("collision_flags")
        if face is None or collision_flag_layer is None:
            self.layout.row().label("No collision face selected.")
        else:
            row = self.layout.row()
            row.label("Collision Flags")
            row.label(str(face[collision_flag_layer]))

class Importer:
    def __init__(self, operator, context, filepath):
        self.operator = operator
        self.context = context
        # Extract path information.
        self.filepath = filepath
        self.directory = os.path.dirname(self.filepath)
        self.filename = os.path.basename(self.filepath)
        self.fileext = os.path.splitext(self.filename)[1].upper()

    def run(self):
        # Read in the file data.
        with open(self.filepath, "rb") as raw:
            kcl_file = KclFile(raw)
        # Import the data into Blender objects.
        self._convert_kcl(kcl_file)
        return {"FINISHED"}

    def _convert_kcl(self, kcl):
        for i in range(0, len(kcl.models)):
            self._convert_model(kcl, i)

    def _convert_model(self, kcl, model_index):
        model = kcl.models[model_index]
        # Load the model data into a bmesh. Create a custom layer for the collision flags in it.
        bm = bmesh.new()
        collision_flag_layer = bm.faces.layers.int.new("collision_flags")
        for triangle in model.triangles:
            vertices = model.get_triangle_vertices(triangle)
            vert1 = bm.verts.new(vertices[0])
            vert2 = bm.verts.new(vertices[1])
            vert3 = bm.verts.new(vertices[2])
            face = bm.faces.new((vert1, vert2, vert3))
            face[collision_flag_layer] = triangle.collision_flags
        # Create the mesh into which the bmesh data will be written.
        mesh = bpy.data.meshes.new("Model" + str(model_index))
        bm.to_mesh(mesh)
        bm.free()
        # Create an object representing that mesh.
        obj = bpy.data.objects.new("Model" + str(model_index), mesh)
        bpy.context.scene.objects.link(obj)
