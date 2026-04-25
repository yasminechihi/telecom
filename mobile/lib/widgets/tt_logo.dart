import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

// ════════════════════════════════════════════════════════════
//  Widget Logo Tunisie Telecom
//  Affiche logo_tt.png avec fallback texte "TT"
// ════════════════════════════════════════════════════════════

class TTLogo extends StatelessWidget {
  final double size;
  final bool onDark;      // true = fond violet, false = fond blanc
  final double radius;

  const TTLogo({
    super.key,
    this.size = 44,
    this.onDark = false,
    this.radius = 10,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: onDark ? Colors.white : TTColors.purple,
        borderRadius: BorderRadius.circular(radius),
        boxShadow: onDark
            ? [BoxShadow(color: Colors.black.withOpacity(0.2), blurRadius: 16, offset: const Offset(0, 4))]
            : null,
      ),
      clipBehavior: Clip.antiAlias,
      child: Image.asset(
        'assets/logo_tt.png',
        fit: BoxFit.contain,
        errorBuilder: (_, __, ___) => Center(
          child: Text(
            'TT',
            style: TextStyle(
              color: onDark ? TTColors.purple : Colors.white,
              fontWeight: FontWeight.w900,
              fontSize: size * 0.38,
              fontFamily: 'Cairo',
            ),
          ),
        ),
      ),
    );
  }
}


// ────────────────────────────────────────────────────────────
//  Version grande (pour la page de login / splash)
// ────────────────────────────────────────────────────────────

class TTLogoBig extends StatelessWidget {
  final double size;

  const TTLogoBig({super.key, this.size = 90});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(size * 0.22),
        boxShadow: [
          BoxShadow(color: Colors.black.withOpacity(0.2), blurRadius: 20, offset: const Offset(0, 6)),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Image.asset(
        'assets/logo_tt.png',
        fit: BoxFit.contain,
        errorBuilder: (_, __, ___) => Center(
          child: Text(
            'TT',
            style: TextStyle(
              color: TTColors.purple,
              fontWeight: FontWeight.w900,
              fontSize: size * 0.42,
              fontFamily: 'Cairo',
            ),
          ),
        ),
      ),
    );
  }
}
