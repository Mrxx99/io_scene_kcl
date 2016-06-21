class Log:
    @staticmethod
    def write(indent, text):
        indent = " " * 2 * indent
        print("KCL: " + indent + text)
