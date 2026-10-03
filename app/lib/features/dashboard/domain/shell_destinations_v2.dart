import 'package:flutter/material.dart';

class ShellDestination {
  const ShellDestination({required this.id, required this.label, required this.icon, required this.description, this.primary = false});
  final String id; final String label; final IconData icon; final String description; final bool primary;
}
abstract final class ShellDestinations {
  static const dashboard = ShellDestination(id:'dashboard',label:'داشبورد',icon:Icons.dashboard_outlined,description:'نمای کلی وضعیت مالی و عملیاتی سازمان.',primary:true);
  static const chartOfAccounts = ShellDestination(id:'chart-of-accounts',label:'سرفصل حساب‌ها',icon:Icons.account_tree_outlined,description:'درخت سرفصل‌ها و حساب‌های تفصیلی.',primary:true);
  static const journalEntry = ShellDestination(id:'journal-entry',label:'اسناد حسابداری',icon:Icons.post_add_outlined,description:'ثبت، بررسی، نهایی‌سازی و معکوس‌سازی اسناد.',primary:true);
  static const ledger = ShellDestination(id:'ledger',label:'دفتر کل',icon:Icons.menu_book_outlined,description:'گردش و مانده حساب‌ها.',primary:true);
  static const trialBalance = ShellDestination(id:'trial-balance',label:'تراز آزمایشی',icon:Icons.balance_outlined,description:'کنترل توازن بدهکار و بستانکار.');
  static const customers = ShellDestination(id:'customers',label:'مشتریان',icon:Icons.people_outline,description:'دفتر مشتریان و مانده حساب.');
  static const invoices = ShellDestination(id:'invoices',label:'فاکتورها',icon:Icons.receipt_long_outlined,description:'فاکتورهای فروش و خرید.');
  static const payments = ShellDestination(id:'payments',label:'دریافت و پرداخت',icon:Icons.payments_outlined,description:'دریافت، پرداخت و تسویه.');
  static const reports = ShellDestination(id:'reports',label:'گزارش‌های مالی',icon:Icons.analytics_outlined,description:'گزارش‌های مالی و مدیریتی.');
  static const errorCenter = ShellDestination(id:'error-center',label:'مرکز خطا',icon:Icons.bug_report_outlined,description:'خطاهای قابل پیگیری و لاگ کامل.');
  static const settings = ShellDestination(id:'settings',label:'تنظیمات',icon:Icons.settings_outlined,description:'سازمان، اشتراک، امنیت و تنظیمات.');
  static const all = <ShellDestination>[dashboard,chartOfAccounts,journalEntry,ledger,trialBalance,customers,invoices,payments,reports,errorCenter,settings];
  static const primaryDestinations = <ShellDestination>[dashboard,chartOfAccounts,journalEntry,ledger];
  static ShellDestination byId(String id) => all.firstWhere((d)=>d.id==id);
}
