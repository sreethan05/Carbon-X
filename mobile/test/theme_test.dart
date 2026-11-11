import 'package:carbonx_mobile/src/theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('mobile theme uses the CarbonX forest identity', () {
    final theme = CarbonXTheme.light;
    expect(theme.useMaterial3, isTrue);
    expect(theme.appBarTheme.backgroundColor, CarbonXTheme.forest);
    expect(theme.scaffoldBackgroundColor, CarbonXTheme.paper);
    expect(theme.colorScheme.brightness, Brightness.light);
  });
}
