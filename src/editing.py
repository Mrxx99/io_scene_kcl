import bmesh
import bpy

class KclEditPanel(bpy.types.Panel):
    bl_context = "EDITMODE"
    bl_label = "Nintendo KCL"
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
        flags_layer = bm.faces.layers.int.get("kcl_flags")
        if face is None or flags_layer is None:
            self.layout.row().label("No KCL face selected.")
        else:
            # Collision flags
            self.layout.prop(context.window_manager, "kcl_flag")
            # Binary
            row = self.layout.row()
            row.label("Binary")
            row.label('{0:08b}'.format(face[flags_layer]))
            # Lakitu
            self.layout.prop(context.window_manager, "kcl_is_lakitu")

kcl_dict = {}

@bpy.app.handlers.persistent
def scene_update_post_handler(scene):
    obj = scene.objects.active
    if obj is None:
        return
    if obj.mode == "EDIT" and obj.type == "MESH":
        # Add one instance of edit bmesh to the global dictionary to retrieve it in update methods.
        bm = kcl_dict.setdefault(obj.name, bmesh.from_edit_mesh(obj.data))
        face = bm.faces.active
        flag_layer = bm.faces.layers.int.get("kcl_flags")
        if face and flag_layer:
            flags = face[flag_layer]
            # Update the flags stored in the window manager.
            bpy.context.window_manager.kcl_flag = flags
            bpy.context.window_manager.kcl_is_lakitu = (flags & 0x0010) != 0 # Bit 5
    else:
        kcl_dict.clear()

def update_kcl_flag(self, context):
    edit_obj = context.edit_object
    bm = kcl_dict.setdefault(edit_obj.name, bmesh.from_edit_mesh(edit_obj.data))
    face = bm.faces.active
    flag_layer = bm.faces.layers.int.get("kcl_flags")
    if face and flag_layer:
        face[flag_layer] = self.kcl_flag

def update_is_lakitu(self, context):
    edit_obj = context.edit_object
    bm = kcl_dict.setdefault(edit_obj.name, bmesh.from_edit_mesh(edit_obj.data))
    face = bm.faces.active
    flag_layer = bm.faces.layers.int.get("kcl_flags")
    if face and flag_layer:
        if self.kcl_is_lakitu:
            self.kcl_flag |= 0x0010
        else:
            self.kcl_flag &= ~0x0010
        face[flag_layer] = self.kcl_flag
