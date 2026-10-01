/// An organization the signed-in user is a member of.
class Organization {
  const Organization({required this.id, required this.name});

  final String id;
  final String name;

  static Organization fromJson(Map<String, Object?> json) {
    final Object? id = json['id'];
    final Object? name = json['name'];
    if (id is! String || id.isEmpty) {
      throw const FormatException('شناسه سازمان در پاسخ سرور معتبر نیست.');
    }
    if (name is! String || name.isEmpty) {
      throw const FormatException('نام سازمان در پاسخ سرور معتبر نیست.');
    }
    return Organization(id: id, name: name);
  }
}