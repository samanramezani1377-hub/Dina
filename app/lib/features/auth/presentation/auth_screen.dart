import 'package:flutter/material.dart';

import '../../../app/api/user_facing_message.dart';
import '../../../app/app_scope.dart';
import 'auth_controller.dart';

/// Login and registration, as one screen pair behind a toggle.
///
/// The screen never decides whether the user is allowed into the app; it only
/// reports the credentials it was given and displays what the backend said.
class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  final TextEditingController _email = TextEditingController();
  final TextEditingController _password = TextEditingController();
  final TextEditingController _displayName = TextEditingController();

  bool _registering = false;
  bool _submitting = false;
  bool _obscurePassword = true;
  String? _errorMessage;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _displayName.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_submitting || !(_formKey.currentState?.validate() ?? false)) {
      return;
    }
    setState(() {
      _submitting = true;
      _errorMessage = null;
    });
    final AuthController controller = AppScope.of(context).authController;
    try {
      if (_registering) {
        await controller.register(
          email: _email.text.trim(),
          password: _password.text,
          displayName: _displayName.text.trim(),
        );
      } else {
        await controller.login(
          email: _email.text.trim(),
          password: _password.text,
        );
      }
    } on Object catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _submitting = false;
        _errorMessage = userFacingMessage(error);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final TextTheme textTheme = Theme.of(context).textTheme;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    Text('دینا', style: textTheme.headlineMedium),
                    const SizedBox(height: 8),
                    Text(
                      _registering
                          ? 'برای ساخت حساب کاربری، اطلاعات زیر را وارد کنید.'
                          : 'برای ورود به حساب کاربری، اطلاعات زیر را وارد کنید.',
                      style: textTheme.bodyMedium,
                    ),
                    const SizedBox(height: 24),
                    if (_registering) ...<Widget>[
                      TextFormField(
                        key: const ValueKey<String>('auth-display-name'),
                        controller: _displayName,
                        textInputAction: TextInputAction.next,
                        decoration: const InputDecoration(
                          labelText: 'نام و نام خانوادگی',
                        ),
                        validator: (String? value) =>
                            (value != null && value.trim().isEmpty)
                            ? 'نام نمی‌تواند خالی باشد.'
                            : null,
                      ),
                      const SizedBox(height: 16),
                    ],
                    TextFormField(
                      key: const ValueKey<String>('auth-email'),
                      controller: _email,
                      keyboardType: TextInputType.emailAddress,
                      textInputAction: TextInputAction.next,
                      autofillHints: const <String>[AutofillHints.email],
                      decoration: const InputDecoration(labelText: 'ایمیل'),
                      validator: _validateEmail,
                    ),
                    const SizedBox(height: 16),
                    TextFormField(
                      key: const ValueKey<String>('auth-password'),
                      controller: _password,
                      obscureText: _obscurePassword,
                      textInputAction: TextInputAction.done,
                      autofillHints: const <String>[AutofillHints.password],
                      onFieldSubmitted: (_) => _submit(),
                      decoration: InputDecoration(
                        labelText: 'گذرواژه',
                        suffixIcon: IconButton(
                          onPressed: () => setState(
                            () => _obscurePassword = !_obscurePassword,
                          ),
                          icon: Icon(
                            _obscurePassword
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined,
                          ),
                          tooltip: _obscurePassword
                              ? 'نمایش گذرواژه'
                              : 'پنهان کردن گذرواژه',
                        ),
                      ),
                      validator: (String? value) =>
                          (value == null || value.isEmpty)
                          ? 'گذرواژه را وارد کنید.'
                          : null,
                    ),
                    if (_errorMessage != null) ...<Widget>[
                      const SizedBox(height: 16),
                      _AuthErrorBanner(message: _errorMessage!),
                    ],
                    const SizedBox(height: 24),
                    FilledButton(
                      key: const ValueKey<String>('auth-submit'),
                      onPressed: _submitting ? null : _submit,
                      child: _submitting
                          ? const SizedBox(
                              height: 20,
                              width: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : Text(_registering ? 'ثبت‌نام' : 'ورود'),
                    ),
                    const SizedBox(height: 8),
                    TextButton(
                      onPressed: _submitting
                          ? null
                          : () => setState(() {
                              _registering = !_registering;
                              _errorMessage = null;
                            }),
                      child: Text(
                        _registering
                            ? 'حساب دارید؟ وارد شوید'
                            : 'حساب ندارید؟ ثبت‌نام کنید',
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  String? _validateEmail(String? value) {
    final String trimmed = (value ?? '').trim();
    if (trimmed.isEmpty) {
      return 'ایمیل را وارد کنید.';
    }
    if (!trimmed.contains('@') || trimmed.startsWith('@') || trimmed.endsWith('@')) {
      return 'ایمیل معتبر نیست.';
    }
    return null;
  }
}

/// Surfaces a rejected sign-in without leaking internals of the client.
class _AuthErrorBanner extends StatelessWidget {
  const _AuthErrorBanner({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: scheme.errorContainer,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: <Widget>[
          Icon(Icons.error_outline, color: scheme.onErrorContainer),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              message,
              style: TextStyle(color: scheme.onErrorContainer),
            ),
          ),
        ],
      ),
    );
  }
}