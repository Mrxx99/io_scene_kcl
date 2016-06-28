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
        return context.mode == "EDIT_MESH" and context.object

    def draw(self, context):
        obj = context.object
        bm = bmesh.from_edit_mesh(obj.data)
        face = bm.faces.active
        flags_layer = bm.faces.layers.int.get("kcl_flags")
        if not face or not flags_layer:
            self.layout.row().label("No KCL face selected.")
        else:
            # Collision flags
            self.layout.prop(context.window_manager, "kcl_flag")
            # Binary
            row = self.layout.row()
            row.label('{0:08b} {1:08b}'.format(face[flags_layer] >> 8, face[flags_layer] & 0xFF))
            # Lakitu
            self.layout.prop(context.window_manager, "kcl_is_lakitu")
            # Select Similar
            self.layout.operator("kcl.select_similar", text='Select Similar')


class KclSelectSimilar(bpy.types.Operator):
    bl_idname = "kcl.select_similar"
    bl_label = "Select Similar"

    def execute(self, context):
        # Get the bmesh instance of the mesh which is currently in edit mode.
        edit_obj = context.edit_object
        bm = kcl_dict.setdefault(edit_obj.name, bmesh.from_edit_mesh(edit_obj.data))
        # Get the collision flag layer.
        flag_layer = bm.faces.layers.int.get("kcl_flags")
        # Find all the faces with the same collision flag.
        faces = [f for f in bm.faces if f[flag_layer] == context.window_manager.kcl_flag]
        for face in faces:
            face.select = True
        return {'FINISHED'}


kcl_dict = {}
kcl_update_by_code = False

@bpy.app.handlers.persistent
def scene_update_post_handler(scene):
    obj = scene.objects.active
    if not obj:
        return
    if obj.mode == "EDIT" and obj.type == "MESH":
        # Ensure to have an instance of the edit bmesh in the global dictionary to retrieve it in update methods.
        bm = kcl_dict.setdefault(obj.name, bmesh.from_edit_mesh(obj.data))
        face = bm.faces.active
        flag_layer = bm.faces.layers.int.get("kcl_flags")
        if face and flag_layer:
            flags = face[flag_layer]
            # Update the flags stored in the window manager.
            kcl_dict["update_by_code"] = True
            bpy.context.window_manager.kcl_flag = flags
            bpy.context.window_manager.kcl_is_lakitu = (flags & 0x0010) != 0 # Bit 5
            kcl_dict["update_by_code"] = False
    else:
        kcl_dict.clear()

def set_flag_for_selected_faces(context, flag):
    # Get the bmesh instance of the mesh which is currently in edit mode.
    edit_obj = context.edit_object
    bm = kcl_dict.setdefault(edit_obj.name, bmesh.from_edit_mesh(edit_obj.data))
    # Get the collision flag layer and selected faces.
    flag_layer = bm.faces.layers.int.get("kcl_flags")
    faces = [f for f in bm.faces if f.select]
    # If layer found and faces selected, set the given flag to all.
    if flag_layer and faces:
        for face in faces:
            face[flag_layer] = flag

def update_kcl_flag(self, context):
    if kcl_dict["update_by_code"]:
        return
    set_flag_for_selected_faces(context, self.kcl_flag)

def update_is_lakitu(self, context):
    if kcl_dict["update_by_code"]:
        return
    if self.kcl_is_lakitu:
        set_flag_for_selected_faces(context, self.kcl_flag | 0x0010)
    else:
        set_flag_for_selected_faces(context, self.kcl_flag & ~0x0010)
