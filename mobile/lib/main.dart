import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'theme/app_theme.dart';
import 'services/api_service.dart';
import 'screens/login_screen.dart';
import 'screens/register_screen.dart';
import 'screens/dashboard_screen.dart';
import 'screens/chat_screen.dart';
import 'widgets/tt_logo.dart';

// ════════════════════════════════════════════════════════════
//  Mon Espace TT — Application Flutter
//  Identique à user_app.py (Flask) — même Firebase Firestore
// ════════════════════════════════════════════════════════════

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Charge l'IP du serveur depuis SharedPreferences au démarrage
  await ApiService().loadServerIp();
  runApp(const TTApp());
}

class TTApp extends StatefulWidget {
  const TTApp({super.key});

  @override
  State<TTApp> createState() => _TTAppState();
}

class _TTAppState extends State<TTApp> {
  // Vérification session au démarrage
  late final GoRouter _router;

  @override
  void initState() {
    super.initState();
    _router = GoRouter(
      initialLocation: '/splash',
      routes: [
        GoRoute(
          path: '/splash',
          builder: (context, state) => const _SplashScreen(),
        ),
        GoRoute(
          path: '/login',
          builder: (context, state) => const LoginScreen(),
        ),
        GoRoute(
          path: '/register',
          builder: (context, state) => const RegisterScreen(),
        ),
        GoRoute(
          path: '/dashboard',
          builder: (context, state) => const DashboardScreen(),
        ),
        GoRoute(
          path: '/chat',
          builder: (context, state) {
            final extra = state.extra as Map<String, dynamic>?;
            return ChatScreen(
              convSessionId: extra?['convSessionId'] as String?,
              existingConvId: extra?['convId'] as String?,
            );
          },
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'Mon Espace TT',
      theme: AppTheme.theme,
      routerConfig: _router,
      debugShowCheckedModeBanner: false,
    );
  }
}


// ════════════════════════════════════════════════════════════
//  Splash Screen — vérifie si l'utilisateur est connecté
// ════════════════════════════════════════════════════════════

class _SplashScreen extends StatefulWidget {
  const _SplashScreen();

  @override
  State<_SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<_SplashScreen> {
  @override
  void initState() {
    super.initState();
    _checkSession();
  }

  Future<void> _checkSession() async {
    await Future.delayed(const Duration(milliseconds: 800));
    if (!mounted) return;
    final loggedIn = await ApiService().isLoggedIn();
    if (!mounted) return;
    context.go(loggedIn ? '/dashboard' : '/login');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF3D1484),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            // Logo Tunisie Telecom
            const TTLogoBig(size: 110),
            const SizedBox(height: 28),
            const Text(
              'Mon Espace TT',
              style: TextStyle(
                fontSize: 26,
                fontWeight: FontWeight.w900,
                color: Colors.white,
                fontFamily: 'Cairo',
              ),
            ),
            const SizedBox(height: 6),
            Text(
              'Tunisie Telecom',
              style: TextStyle(
                fontSize: 14,
                color: Colors.white.withOpacity(0.75),
                fontFamily: 'Cairo',
              ),
            ),
            const SizedBox(height: 50),
            const CircularProgressIndicator(
              valueColor: AlwaysStoppedAnimation<Color>(Color(0xFF00B4D8)),
              strokeWidth: 2.5,
            ),
          ],
        ),
      ),
    );
  }
}
