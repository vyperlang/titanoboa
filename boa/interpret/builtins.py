

class BuiltinFunction:
    _id: str

class Empty(BuiltinFunction):
    _id = "empty"

    def eval(self, context, type_expr):
        typ = get_type_from_annotation(type_expr)
        return VyperObject.empty(new_type_to_old_type(typ))

DISPATCH = {
    "empty": Empty(),
}
