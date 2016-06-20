import bmesh
import bpy
import bpy_extras
import os
from .log import Log
from .kcl_file import KclFile

class ImportOperator(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
    bl_idname = "import_scene.bfres"
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
        # Load the model data into a bmesh.
        bm = bmesh.new()
        for triangle in model.triangles:
            vertices = model.get_triangle_vertices(triangle)
            vert1 = bm.verts.new(vertices[0])
            vert2 = bm.verts.new(vertices[1])
            vert3 = bm.verts.new(vertices[2])
            bm.faces.new((vert1, vert2, vert3))
        # Create the mesh into which the bmesh data will be written.
        mesh = bpy.data.meshes.new("Model" + str(model_index))
        bm.to_mesh(mesh)
        bm.free()
        # Create an object representing that mesh.
        obj = bpy.data.objects.new("Model" + str(model_index), mesh)
        bpy.context.scene.objects.link(obj)
