import io
from mathutils import Vector
from .binary_io import BinaryReader

class KclFile:
    class Header:
        def __init__(self, reader):
            if reader.read_uint32() != 0x02020000:
                raise AssertionError("Invalid KCL header.")
            self.model_octree_offset = reader.read_uint32()
            self.model_offset_array_offset = reader.read_uint32()
            self.model_count = reader.read_uint32()
            self.min_model_coordinate = reader.read_vector3f()
            self.max_model_coordinate = reader.read_vector3f()
            self.coordinate_shift = reader.read_vector3() # Unsure
            self.unknown0x34 = reader.read_uint32()

    def __init__(self, raw):
        # Open a big-endian binary reader on the stream.
        with BinaryReader(raw) as reader:
            reader.endianness = ">"
            self.header = self.Header(reader)
            # Load the model offset list.
            reader.seek(self.header.model_offset_array_offset)
            self.model_offsets = reader.read_uint32s(self.header.model_count)
            # Load the models.
            self.models = []
            for i in range(0, len(self.model_offsets)):
                reader.seek(self.model_offsets[i])
                self.models.append(KclModel(reader))

class KclModel:
    class Header:
        def __init__(self, reader):
            offset = reader.tell() # Offsets relative to start of model.
            self.positions_offset = offset + reader.read_uint32()
            self.normals_offset = offset + reader.read_uint32()
            self.triangles_offset = offset + reader.read_uint32()
            self.octree_offset = offset + reader.read_uint32()
            self.unknown0x10 = reader.read_single()
            self.first_spatial_position = reader.read_vector3f()
            self.mask = reader.read_vector3()
            self.shift = reader.read_vector3()
            self.unknown0x38 = reader.read_single()

    class Triangle:
        def __init__(self, reader):
            self.length = reader.read_single()
            self.position_index = reader.read_uint16()
            self.direction_index = reader.read_uint16()
            self.normal_a_index = reader.read_uint16()
            self.normal_b_index = reader.read_uint16()
            self.normal_c_index = reader.read_uint16()
            self.collision_flags = reader.read_uint16()
            self.global_index = reader.read_uint32()

        def write(self, writer):
            writer.write_single(self.length)
            writer.write_uint16(self.position_index)
            writer.write_uint16(self.direction_index)
            writer.write_uint16(self.normal_a_index)
            writer.write_uint16(self.normal_b_index)
            writer.write_uint16(self.normal_c_index)
            writer.write_uint16(self.collision_flags)
            writer.write_uint32(self.global_index)

    class OctreeNode:
        def __init__(self, base, width, bm, indices, max_triangles, min_width):
            self.half_width = width / 2.0
            self.c = base + Vector((self.half_width, self.half_width, self.half_width))
            self.is_leaf = True
            self.indices = []
            for i in indices:
                # TODO: Maybe solving it with a Wiimm KCL_BLOW approach is faster.
                if self.tricube_overlap(bm.faces[i], self):
                    self.indices.append(i)
            # Split this node's cube when it contains too many triangles and the minimum size is not underrun yet.
            if len(self.indices) > max_triangles and self.half_width >= min_width:
                self.is_leaf = False
                self.branches = [KclModel.OctreeNode(base + (Vector((x, y, z)) * self.half_width), self.half_width,
                     bm, self.indices,
                     max_triangles, min_width)
                     for z in range(0, 2) for y in range(0, 2) for x in range(0, 2)]
                self.indices = []

        def write(self, writer, base_address):
            pos = writer.tell()
            writer.seek(0, io.SEEK_END)
            end_position = writer.tell()
            if self.is_leaf:
                # Write the offset back at this nodes address.
                writer.seek(pos)
                writer.write_uint32((end_position - base_address - 2) | 0x80000000)
                writer.seek(end_position + 4)
                # Write the triangle indices and terminate the list with 0xFFFF.
                writer.write_uint16s(self.indices)
                writer.write_uint16(0xFFFF)
            else:
                writer.seek(pos)
                writer.write_uint32(end_position - base_address)
                writer.seek(end_position + 4)
                base = writer.tell()
                writer.write_uint32s([0x00000000] * 8)
                writer.seek(base)
                for node in self.branches:
                    node.write(writer, base)
            writer.seek(pos + 4)

        @staticmethod
        def tricube_overlap(bm_face, cube):
            # Intersection test for triangle and axis-aligned cube.
            def axis_test(a1, a2, b1, b2, c1, c2):
                p = a1 * b1 + a2 * b2
                q = a1 * c1 + a2 * c2
                r = cube.half_width * (abs(a1) + abs(a2))
                return min(p, q) > r or max(p, q) < -r

            v0 = bm_face.verts[0].co - cube.c
            v1 = bm_face.verts[1].co - cube.c
            v2 = bm_face.verts[2].co - cube.c
            if min(v0.x, v1.x, v2.x) > cube.half_width or max(v0.x, v1.x, v2.x) < -cube.half_width: return False
            if min(v0.y, v1.y, v2.y) > cube.half_width or max(v0.y, v1.y, v2.y) < -cube.half_width: return False
            if min(v0.z, v1.z, v2.z) > cube.half_width or max(v0.z, v1.z, v2.z) < -cube.half_width: return False
            d = bm_face.normal.dot(v0)
            r = cube.half_width * (abs(bm_face.normal.x) + abs(bm_face.normal.y) + abs(bm_face.normal.z))
            if d > r or d < -r: return False
            e = v1 - v0
            if axis_test(e.z, -e.y, v0.y, v0.z, v2.y, v2.z): return False
            if axis_test(-e.z, e.x, v0.x, v0.z, v2.x, v2.z): return False
            if axis_test(e.y, -e.x, v1.x, v1.y, v2.x, v2.y): return False
            e = v2 - v1
            if axis_test(e.z, -e.y, v0.y, v0.z, v2.y, v2.z): return False
            if axis_test(-e.z, e.x, v0.x, v0.z, v2.x, v2.z): return False
            if axis_test(e.y, -e.x, v0.x, v0.y, v1.x, v1.y): return False
            e = v0 - v2
            if axis_test(e.z, -e.y, v0.y, v0.z, v1.y, v1.z): return False
            if axis_test(-e.z, e.x, v0.x, v0.z, v1.x, v1.z): return False
            if axis_test(e.y, -e.x, v1.x, v1.y, v2.x, v2.y): return False
            return True

    def __init__(self, reader):
        self.header = self.Header(reader)
        # Load the positions of the vertices.
        reader.seek(self.header.positions_offset)
        self.positions = []
        position_count = (self.header.normals_offset - self.header.positions_offset) // 12
        for i in range(0, position_count):
            self.positions.append(reader.read_vector_3d())
        # Load the normals.
        self.normals = []
        reader.seek(self.header.normals_offset)
        normal_count = (self.header.triangles_offset - self.header.normals_offset + 0x10) // 12
        for i in range(0, normal_count):
            self.normals.append(reader.read_vector_3d())
        # Read the triangles.
        self.triangles = []
        reader.seek(self.header.triangles_offset)
        triangle_count = (self.header.octree_offset - self.header.triangles_offset) // 20
        for i in range(0, triangle_count):
            self.triangles.append(self.Triangle(reader))

    def get_triangle_vertices(self, triangle):
        position = self.positions[triangle.position_index]
        direction = self.normals[triangle.direction_index]
        normal_a = self.normals[triangle.normal_a_index]
        normal_b = self.normals[triangle.normal_b_index]
        normal_c = self.normals[triangle.normal_c_index]
        cross_a = normal_a.cross(direction)
        cross_b = normal_b.cross(direction)
        vertex1 = position.copy()
        vertex2 = position + cross_b * (triangle.length / cross_b.dot(normal_c))
        vertex3 = position + cross_a * (triangle.length / cross_a.dot(normal_c))
        return vertex1, vertex2, vertex3
