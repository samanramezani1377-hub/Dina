import 'package:flutter/material.dart';
class ShellDestination {
  const ShellDestination({required this.id,required this.label,required this.icon,required this.description,this.primary=false});
  final String id,label,description; final IconData icon; final bool primary;
}
abstract final class ShellDestinations {
  static const dashboard=ShellDestination(id:'dashboard',label:'داشبورد',icon:Icons.dashboard_outlined,description:'نمای کلی وضعیت مالی و عملیاتی.',primary:true);
  static const chart=ShellDestination(id:'chart-of-accounts',label:'سرفصل حساب‌ها',icon:Icons.account_tree_outlined,description:'درخت حساب‌ها.',primary:true);
  static const journal=ShellDestination(id:'journal-entry',label:'اسناد حسابداری',icon:Icons.post_add_outlined,description:'ثبت و مدیریت اسناد.',primary:true);
  static const ledger=ShellDestination(id:'ledger',label:'دفتر کل',icon:Icons.menu_book_outlined,description:'گردش و مانده حساب‌ها.',primary:true);
  static const trial=ShellDestination(id:'trial-balance',label:'تراز آزمایشی',icon:Icons.balance_outlined,description:'کنترل توازن.');
  static const customers=ShellDestination(id:'customers',label:'مشتریان',icon:Icons.people_outline,description:'دفتر مشتریان.');
  static const invoices=ShellDestination(id:'invoices',label:'فاکتورها',icon:Icons.receipt_long_outlined,description:'فروش و خرید.');
  static const payments=ShellDestination(id:'payments',label:'دریافت و پرداخت',icon:Icons.payments_outlined,description:'تسویه‌ها.');
  static const reports=ShellDestination(id:'reports',label:'گزارش‌ها',icon:Icons.analytics_outlined,description:'گزارش‌های مالی.');
  static const management=ShellDestination(id:'management',label:'مدیریت',icon:Icons.admin_panel_settings_outlined,description:'مدیریت سازمان، اشتراک و رویدادها.');
  static const errors=ShellDestination(id:'error-center',label:'مرکز خطا',icon:Icons.bug_report_outlined,description:'خطاها و لاگ‌های تشخیصی.');
  static const settings=ShellDestination(id:'settings',label:'تنظیمات',icon:Icons.settings_outlined,description:'تنظیمات سازمان و حساب.');
  static const all=<ShellDestination>[dashboard,chart,journal,ledger,trial,customers,invoices,payments,reports,management,errors,settings];
  static const primaryDestinations=<ShellDestination>[dashboard,chart,journal,ledger];
  static ShellDestination byId(String id)=>all.firstWhere((d)=>d.id==id);
}
