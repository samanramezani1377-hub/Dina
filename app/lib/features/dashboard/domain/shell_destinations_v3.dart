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
  static const suppliers=ShellDestination(id:'suppliers',label:'تأمین‌کنندگان',icon:Icons.local_shipping_outlined,description:'دفتر تأمین‌کنندگان.');
  static const products=ShellDestination(id:'products',label:'کالا و خدمات',icon:Icons.inventory_2_outlined,description:'کالاها و خدمات.');
  static const warehouses=ShellDestination(id:'warehouses',label:'انبارها',icon:Icons.warehouse_outlined,description:'مدیریت انبارها.');
  static const inventory=ShellDestination(id:'inventory',label:'موجودی کالا',icon:Icons.inventory_outlined,description:'موجودی و گردش کالا.');
  static const cash=ShellDestination(id:'cash-accounts',label:'صندوق و بانک',icon:Icons.account_balance_outlined,description:'صندوق‌ها و حساب‌های بانکی.');
  static const checks=ShellDestination(id:'checks',label:'چک‌ها',icon:Icons.fact_check_outlined,description:'دریافتی و پرداختی.');
  static const sales=ShellDestination(id:'sales',label:'فروش',icon:Icons.point_of_sale_outlined,description:'فاکتورهای فروش.');
  static const purchases=ShellDestination(id:'purchases',label:'خرید',icon:Icons.shopping_cart_outlined,description:'فاکتورهای خرید.');
  static const fiscalYears=ShellDestination(id:'fiscal-years',label:'سال مالی',icon:Icons.event_note_outlined,description:'دوره‌های مالی و بستن سال.');
  static const customers=ShellDestination(id:'customers',label:'مشتریان',icon:Icons.people_outline,description:'دفتر مشتریان.');
  static const invoices=ShellDestination(id:'invoices',label:'فاکتورها',icon:Icons.receipt_long_outlined,description:'فروش و خرید.');
  static const payments=ShellDestination(id:'payments',label:'دریافت و پرداخت',icon:Icons.payments_outlined,description:'تسویه‌ها.');
  static const reports=ShellDestination(id:'reports',label:'گزارش‌ها',icon:Icons.analytics_outlined,description:'گزارش‌های مالی.');
  static const management=ShellDestination(id:'management',label:'مدیریت',icon:Icons.admin_panel_settings_outlined,description:'مدیریت سازمان، اشتراک و رویدادها.');
  static const platformAdmin=ShellDestination(id:'platform-admin',label:'مدیریت پلتفرم',icon:Icons.security_outlined,description:'کنترل کاربران، سازمان‌ها، پلن‌ها و پرداخت‌ها.');
  static const errors=ShellDestination(id:'error-center',label:'مرکز خطا',icon:Icons.bug_report_outlined,description:'خطاها و لاگ‌های تشخیصی.');
  static const settings=ShellDestination(id:'settings',label:'تنظیمات',icon:Icons.settings_outlined,description:'تنظیمات سازمان و حساب.');
  static const all=<ShellDestination>[dashboard,chart,journal,ledger,trial,customers,suppliers,products,warehouses,inventory,cash,checks,sales,purchases,fiscalYears,invoices,payments,reports,management,platformAdmin,errors,settings];
  static const primaryDestinations=<ShellDestination>[dashboard,chart,journal,ledger];
  static ShellDestination byId(String id)=>all.firstWhere((d)=>d.id==id);
}
