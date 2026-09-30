import 'package:flutter/material.dart';

void main() {
  runApp(const DinaApp());
}

class DinaApp extends StatelessWidget {
  const DinaApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'دینا',
      debugShowCheckedModeBanner: false,
      home: Scaffold(
        appBar: AppBar(title: const Text('دینا')),
        body: const Center(child: Text('دینا آماده اتصال به Backend است.')),
      ),
    );
  }
}
