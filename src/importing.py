import bmesh
import bpy
import bpy_extras
import os
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

    merge_models = bpy.props.BoolProperty(
        name="Merge Models",
        description="Merges the separate models into one.",
        default=True
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
        self.filename = os.path.basename(self.filepath)

    def run(self):
        # Read in the file data.
        with open(self.filepath, "rb") as raw:
            kcl_file = KclFile(raw)
        # Import the data into Blender objects.
        self._convert_kcl(kcl_file)
        return {"FINISHED"}

    def _convert_kcl(self, kcl):
        # Create an empty object which will hold the child model(s).
        obj = bpy.data.objects.new("KCL", None)
        bpy.context.scene.objects.link(obj)
        # Convert the models and attach them to the empty object.
        global_bm = None
        for i in range(0, len(kcl.models)):
            if self.operator.merge_models:
                # Write all models into one global bmesh spanning them all.
                if global_bm is None:
                    global_bm = self._new_bmesh()
                self._convert_model(global_bm, kcl, i)
            else:
                model_bm = self._new_bmesh()
                self._convert_model(model_bm, kcl, i)
                self._create_mesh_object(model_bm, "Model " + str(i).zfill(2), obj)
        # Create an object for merged models.
        if self.operator.merge_models:
            self._create_mesh_object(global_bm, "Model", obj)

    def _new_bmesh(self):
        bm = bmesh.new()
        bm.faces.layers.int.new("kcl_model_index")
        bm.faces.layers.int.new("kcl_face_index")
        bm.faces.layers.int.new("kcl_flags")
        return bm

    def _convert_model(self, bm, kcl, model_index):
        # Get the additional data layers to keep track of the triangles for exporting.
        model_index_layer = bm.faces.layers.int["kcl_model_index"]
        face_index_layer = bm.faces.layers.int["kcl_face_index"]
        flags_layer = bm.faces.layers.int["kcl_flags"]
        # Add the model to the bmesh.
        kcl_model = kcl.models[model_index]
        for i, triangle in enumerate(kcl_model.triangles):
            vertices = kcl_model.get_triangle_vertices(triangle)
            vert1 = bm.verts.new(vertices[0])
            vert2 = bm.verts.new(vertices[1])
            vert3 = bm.verts.new(vertices[2])
            face = bm.faces.new((vert1, vert2, vert3))
            # Remember the model and face indices.
            face[model_index_layer] = model_index
            face[face_index_layer] = i
            face[flags_layer] = triangle.collision_flags
            # TODO: Assign the material.

    def _create_mesh_object(self, bm, name, parent):
        # Transform the coordinate system so that Y is up.
        matrix_y_to_z = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))
        bmesh.ops.transform(bm, matrix=matrix_y_to_z, verts=bm.verts)
        # Create the mesh into which each bmesh will be written.
        mesh = bpy.data.meshes.new(name)
        bm.to_mesh(mesh)
        bm.free()
        # Create an object representing that mesh.
        mesh_obj = bpy.data.objects.new(name, mesh)
        mesh_obj.parent = parent
        bpy.context.scene.objects.link(mesh_obj)
