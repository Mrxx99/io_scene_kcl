import bmesh
import bpy

class KclEditPanel(bpy.types.Panel):
    bl_context = "EDITMODE"
    bl_label = "KCL"
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
