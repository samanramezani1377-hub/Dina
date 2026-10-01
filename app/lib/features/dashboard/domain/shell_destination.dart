import 'package:flutter/material.dart';

/// A top-level destination in the shell.
///
/// Every destination declares whether it is built. The ones that are not built
/// render an explicit "not implemented" placeholder — the shell never invents a
/// screen, and never shows sample figures for a feature that does not exist.
class ShellDestination {
  const ShellDestination({
    required this.id,
    required this.label,
    required this.icon,
    required this.description,
    this.implemented = false,
    this.primary = false,
  });

  final String id;
  final String label;
  final IconData icon;

  /// What this screen will do once implemented, shown on the placeholder so the
  /// navigation entry explains itself.
  final String description;

  final bool implemented;

  /// Whether the destination is offered in the narrow-width bottom bar. The
  /// bottom bar cannot hold nine items without becoming unusable, so secondary
  /// destinations live behind the overflow sheet.
  final bool primary;
}

/// The full navigation map of the client.
abstract final class ShellDestinations {
  static const ShellDestination dashboard = ShellDestination(
    id: 'dashboard',
    label: 'داشبورد',
    icon: Icons.dashboard_outlined,
    description: 'خلاصه وضعیت مالی سازمان انتخاب‌شده.',
    implemented: true,
    primary: true,
  );

  static const ShellDestination chartOfAccounts = ShellDestination(
    id: 'chart-of-accounts',
    label: 'سرفصل حساب‌ها',
    icon: Icons.account_tree_outlined,
    description:
        'تعریف و درخت‌سازی سرفصل‌های حساب‌ها برای سازمان انتخاب‌شده.',
    primary: true,
  );

  static const ShellDestination journalEntry = ShellDestination(
    id: 'journal-entry',
    label: 'سند حسابداری',
    icon: Icons.post_add_outlined,
    description: 'ثبت، بررسی و ثبت نهایی اسناد حسابداری دوطرفه.',
    primary: true,
  );

  static const ShellDestination ledger = ShellDestination(
    id: 'ledger',
    label: 'دفتر کل',
    icon: Icons.menu_book_outlined,
    description: 'گردش و مانده هر حساب بر پایه اسناد ثبت‌شده.',
    primary: true,
  );

  static const ShellDestination trialBalance = ShellDestination(
    id: 'trial-balance',
    label: 'تراز آزمایشی',
    icon: Icons.balance_outlined,
    description: 'مقایسه مجموع بدهکار و بستانکار در یک دوره مالی.',
  );

  static const ShellDestination customers = ShellDestination(
    id: 'customers',
    label: 'مشتریان',
    icon: Icons.people_outline,
    description: 'ثبت و نگهداری مشتریان و وضعیت حساب آن‌ها.',
  );

  static const ShellDestination invoices = ShellDestination(
    id: 'invoices',
    label: 'فاکتورها',
    icon: Icons.receipt_long_outlined,
    description: 'فاکتورهای فروش و خرید و پیوند آن‌ها به اسناد حسابداری.',
  );

  static const ShellDestination payments = ShellDestination(
    id: 'payments',
    label: 'پرداخت‌ها',
    icon: Icons.payments_outlined,
    description: 'دریافت و پرداخت، تسویه حساب مشتریان و تأمین‌کنندگان.',
  );

  static const ShellDestination settings = ShellDestination(
    id: 'settings',
    label: 'تنظیمات',
    icon: Icons.settings_outlined,
    description: 'اطلاعات کاربر، سازمان‌ها و تنظیمات برنامه.',
  );

  static const List<ShellDestination> all = <ShellDestination>[
    dashboard,
    chartOfAccounts,
    journalEntry,
    ledger,
    trialBalance,
    customers,
    invoices,
    payments,
    settings,
  ];

  static List<ShellDestination> get primaryDestinations => all
      .where((ShellDestination d) => d.primary)
      .toList(growable: false);

  static ShellDestination byId(String id) =>
      all.firstWhere((ShellDestination d) => d.id == id);
}