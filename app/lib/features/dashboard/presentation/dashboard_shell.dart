import 'package:flutter/material.dart';

import '../../../app/app_scope.dart';
import '../../../app/theme/app_theme.dart';
import '../../auth/presentation/auth_controller.dart';
import '../../organizations/domain/organization.dart';
import '../domain/shell_destinations_v3.dart';
import 'dashboard_pages.dart';

/// The authenticated application shell.
///
/// Narrow widths get a bottom bar and a single column; wide widths get a side
/// panel and a two-column frame. The two are different layouts, not one layout
/// stretched, so a resizable desktop window stays usable.
class DashboardShell extends StatefulWidget {
  const DashboardShell({super.key});

  @override
  State<DashboardShell> createState() => _DashboardShellState();
}

class _DashboardShellState extends State<DashboardShell> {
  String _selectedDestinationId = ShellDestinations.dashboard.id;

  ShellDestination get _selected => ShellDestinations.byId(_selectedDestinationId);

  void _select(String destinationId) {
    setState(() => _selectedDestinationId = destinationId);
  }

  @override
  Widget build(BuildContext context) {
    final AppScope scope = AppScope.of(context);
    final AuthController auth = scope.authController;
    final String organizationName = organizationNameFor(scope);
    final String userLabel = auth.user?.label ?? '';

    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        final bool wide = Breakpoints.isWide(constraints.maxWidth);
        return Scaffold(
          appBar: AppBar(
            title: Text(_selected.label),
            actions: wide
                ? <Widget>[]
                : <Widget>[
                    IconButton(
                      onPressed: auth.changeOrganization,
                      icon: const Icon(Icons.swap_horiz),
                      tooltip: 'تغییر سازمان',
                    ),
                    IconButton(
                      onPressed: auth.logout,
                      icon: const Icon(Icons.logout),
                      tooltip: 'خروج از حساب',
                    ),
                  ],
          ),
          body: wide
              ? Row(
                  children: <Widget>[
                    _SidePanel(
                      selectedId: _selectedDestinationId,
                      extended: Breakpoints.isExtendedRail(constraints.maxWidth),
                      organizationName: organizationName,
                      userLabel: userLabel,
                      onSelect: _select,
                      onChangeOrganization: auth.changeOrganization,
                      onLogout: auth.logout,
                    ),
                    const VerticalDivider(width: 1),
                    Expanded(child: _DestinationBody(destination: _selected)),
                  ],
                )
              : _DestinationBody(destination: _selected),
          bottomNavigationBar: wide
              ? null
              : _BottomNavigation(
                  selectedId: _selectedDestinationId,
                  onSelect: _select,
                  onMore: () => _showOverflowSheet(context),
                ),
        );
      },
    );
  }

  Future<void> _showOverflowSheet(BuildContext context) async {
    final List<ShellDestination> secondary = ShellDestinations.all
        .where((ShellDestination d) => !d.primary)
        .toList(growable: false);
    final String? picked = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (BuildContext sheetContext) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          children: <Widget>[
            for (final ShellDestination destination in secondary)
              ListTile(
                key: ValueKey<String>('more-${destination.id}'),
                leading: Icon(destination.icon),
                title: Text(destination.label),
                onTap: () => Navigator.of(sheetContext).pop(destination.id),
              ),
          ],
        ),
      ),
    );
    if (picked != null) {
      _select(picked);
    }
  }
}

/// The name of the selected tenant, resolved from the membership list the server
/// returned. When the name is not in hand the id is shown rather than a guess.
String organizationNameFor(AppScope scope) {
  final String? organizationId = scope.authController.selectedOrganizationId;
  if (organizationId == null || organizationId.isEmpty) {
    return 'سازمان انتخاب‌شده';
  }
  for (final Organization organization
      in scope.organizationController.organizations) {
    if (organization.id == organizationId) {
      return organization.name;
    }
  }
  return organizationId;
}

/// Renders the body for the selected destination, honestly.
class _DestinationBody extends StatelessWidget {
  const _DestinationBody({required this.destination});

  final ShellDestination destination;

  @override
  Widget build(BuildContext context) {
    final AppScope scope = AppScope.of(context);
    if (destination.id == 'dashboard') {
      return DashboardHomePage(
        key: const ValueKey<String>('dashboard-home'),
        organizationName: organizationNameFor(scope),
        userLabel: scope.authController.user?.label ?? '',
      );
    }
    return AccountingWorkspace(
      key: ValueKey<String>('workspace-${destination.id}'),
      destinationId: destination.id,
    );
  }
}

/// Wide-width navigation: a labelled side panel, optional labels on the rail.
class _SidePanel extends StatelessWidget {
  const _SidePanel({
    required this.selectedId,
    required this.extended,
    required this.organizationName,
    required this.userLabel,
    required this.onSelect,
    required this.onChangeOrganization,
    required this.onLogout,
  });

  final String selectedId;
  final bool extended;
  final String organizationName;
  final String userLabel;
  final ValueChanged<String> onSelect;
  final VoidCallback onChangeOrganization;
  final VoidCallback onLogout;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return Container(
      width: extended ? 248 : 96,
      color: scheme.surfaceContainerLow,
      child: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: extended
                    ? CrossAxisAlignment.start
                    : CrossAxisAlignment.center,
                children: <Widget>[
                  Text(
                    'دینا',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  if (extended) ...<Widget>[
                    const SizedBox(height: 4),
                    Text(
                      organizationName,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                    Text(
                      userLabel,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ],
              ),
            ),
            Expanded(
              child: ListView(
                key: const ValueKey<String>('wide-navigation'),
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                children: <Widget>[
                  for (final ShellDestination destination
                      in ShellDestinations.all)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 2),
                      child: extended
                          ? ListTile(
                              selected: destination.id == selectedId,
                              leading: Icon(destination.icon),
                              title: Text(destination.label),
                              onTap: () => onSelect(destination.id),
                            )
                          : Tooltip(
                              message: destination.label,
                              child: IconButton(
                                isSelected: destination.id == selectedId,
                                icon: Icon(destination.icon),
                                onPressed: () => onSelect(destination.id),
                              ),
                            ),
                    ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: extended
                  ? Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: <Widget>[
                        TextButton.icon(
                          onPressed: onChangeOrganization,
                          icon: const Icon(Icons.swap_horiz),
                          label: const Text('تغییر سازمان'),
                        ),
                        TextButton.icon(
                          onPressed: onLogout,
                          icon: const Icon(Icons.logout),
                          label: const Text('خروج'),
                        ),
                      ],
                    )
                  : Row(
                      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                      children: <Widget>[
                        IconButton(
                          onPressed: onChangeOrganization,
                          icon: const Icon(Icons.swap_horiz),
                          tooltip: 'تغییر سازمان',
                        ),
                        IconButton(
                          onPressed: onLogout,
                          icon: const Icon(Icons.logout),
                          tooltip: 'خروج از حساب',
                        ),
                      ],
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Narrow-width navigation: a bottom bar of the primary destinations with an
/// overflow entry for the rest, so nine items never have to share one row.
class _BottomNavigation extends StatelessWidget {
  const _BottomNavigation({
    required this.selectedId,
    required this.onSelect,
    required this.onMore,
  });

  final String selectedId;
  final ValueChanged<String> onSelect;
  final VoidCallback onMore;

  @override
  Widget build(BuildContext context) {
    const List<ShellDestination> primary = ShellDestinations.primaryDestinations;
    final int selectedIndex = primary.indexWhere(
      (ShellDestination d) => d.id == selectedId,
    );
    return NavigationBar(
      key: const ValueKey<String>('narrow-navigation'),
      selectedIndex: selectedIndex < 0 ? primary.length : selectedIndex,
      onDestinationSelected: (int index) {
        if (index < primary.length) {
          onSelect(primary[index].id);
        } else {
          onMore();
        }
      },
      destinations: <Widget>[
        for (final ShellDestination destination in primary)
          NavigationDestination(
            key: ValueKey<String>('bottom-${destination.id}'),
            icon: Icon(destination.icon),
            label: destination.label,
          ),
        const NavigationDestination(
          key: ValueKey<String>('bottom-more'),
          icon: Icon(Icons.more_horiz),
          label: 'بیشتر',
        ),
      ],
    );
  }
}