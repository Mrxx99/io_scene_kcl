import enum
from .log import Log
from .binary_io import BinaryReader

class KclFile:
    class Header:
        def __init__(self, reader):
            if reader.read_uint32() != 0x02020000:
                raise AssertionError("Invalid KCL header.")
            self.octree_offset = reader.read_uint32()
            self.model_offset_list_offset = reader.read_uint32()
            self.model_count = reader.read_uint32()
            self.minimal_model_coordinate = reader.read_vector3f()
            self.maximal_model_coordinate = reader.read_vector3f()
            self.coordinate_shift = reader.read_vector3() # Unsure
            self.unknown0x34 = reader.read_uint32()

    def __init__(self, raw):
        # Open a big-endian binary reader on the stream.
        with BinaryReader(raw) as reader:
            reader.endianness = ">"
            self.header = self.Header(reader)
            # TODO: Load the octree.
            reader.seek(self.header.octree_offset)
            # Load the model offset list.
            reader.seek(self.header.model_offset_list_offset)
            self.model_offsets = []
            for i in range(0, self.header.model_count):
                self.model_offsets.append( reader.read_uint32())
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
            self.section_4_offset = offset + reader.read_uint32()
            self.unknown0x10 = reader.read_single()
            self.first_spatial_coordinate = reader.read_vector3f()
            self.mask = reader.read_vector3()
            self.coordinate_shift = reader.read_vector3()
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
            self.unknown0x10 = reader.read_uint32()

    def __init__(self, reader):
        self.header = self.Header(reader)
        # Load the positions of the vertices.
        reader.seek(self.header.positions_offset)
        self.positions = []
        position_count = (self.header.normals_offset - self.header.positions_offset) // 12
        for i in range(0, position_count):
            self.positions.append(reader.read_vector_3d())
        # Load the normals.
        reader.seek(self.header.normals_offset)
        self.normals = []
        normal_count = (self.header.triangles_offset - self.header.normals_offset + 0x10) // 12
        for i in range(0, normal_count):
            self.normals.append(reader.read_vector_3d())
        # Read the triangles.
        reader.seek(self.header.triangles_offset)
        self.triangles = []
        triangle_count = (self.header.section_4_offset - self.header.triangles_offset) // 20
        for i in range(0, triangle_count):
            self.triangles.append(self.Triangle(reader))

    def get_triangle_vertices(self, triangle):
        normal_a = self.normals[triangle.normal_a_index]
        normal_b = self.normals[triangle.normal_b_index]
        normal_c = self.normals[triangle.normal_c_index]
        direction = self.normals[triangle.direction_index]
        position = self.positions[triangle.position_index]
        cross_a = normal_a.cross(direction)
        cross_b = normal_b.cross(direction)
        vertex1 = position.copy()
        vertex2 = position + cross_b * (triangle.length / cross_b.dot(normal_c))
        vertex3 = position + cross_a * (triangle.length / cross_a.dot(normal_c))
        # Exchange Y with Z.
        vertex1 = vertex1.xzy
        vertex1.y = -vertex1.y
        vertex2 = vertex2.xzy
        vertex2.y = -vertex2.y
        vertex3 = vertex3.xzy
        vertex3.y = -vertex3.y
        return vertex1, vertex2, vertex3

    def get_vertices_triangle(self, vertex1, vertex2, vertex3):
        position = vertex1.copy()
        direction = (vertex2 - vertex1).cross(vertex3 - vertex1).normalized()
        normal_a = direction.cross(vertex3 - vertex1).normalized()
        normal_b = -direction.cross(vertex2 - vertex1).normalized()
        normal_c = direction.cross(vertex2 - vertex3).normalized()
        length = (vertex2 - vertex1).dot(normal_c)
        # TODO: Return this in a useful way for an exporter later on.
        return length, position, direction, normal_a, normal_b, normal_c
