import bmesh
import bpy
import bpy_extras
from mathutils import Matrix
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

    @staticmethod
    def menu_func_import(self, context):
        self.layout.operator(ImportOperator.bl_idname, text="Nintendo KCL (.kcl)")

    def execute(self, context):
        importer = Importer(self, context, self.properties.filepath)
        return importer.run()

class Importer:
    def __init__(self, operator, context, filepath):
        self.operator = operator
        self.context = context
        self.filepath = filepath

    def run(self):
        # Read in the file data.
        with open(self.filepath, "rb") as raw:
            kcl_file = KclFile(raw)
        # Import the data into Blender objects.
        self._convert_kcl(kcl_file)
        return {"FINISHED"}

    def _convert_kcl(self, kcl):
        # Create all models as mesh children of an empty object.
        obj = bpy.data.objects.new("KCL", None)
        bpy.context.scene.objects.link(obj)
        # Convert the models and attach them to the empty object.
        for i in range(0, len(kcl.models)):
            self._convert_model(obj, kcl, i)

    def _convert_model(self, parent_obj, kcl, model_index):
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
        # Transform the coordinate system so that Y is up.
        matrix_y_to_z = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))
        bmesh.ops.transform(bm, matrix=matrix_y_to_z, verts=bm.verts)
        # Create the mesh into which the bmesh data will be written.
        mesh = bpy.data.meshes.new("Model" + str(model_index))
        bm.to_mesh(mesh)
        bm.free()
        # Create an object representing that mesh.
        obj = bpy.data.objects.new("Model" + str(model_index), mesh)
        obj.parent = parent_obj
        bpy.context.scene.objects.link(obj)
