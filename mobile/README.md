# CarbonX Mobile

Flutter Material 3 client for the existing CarbonX FastAPI backend.

## First-time platform setup

The Android and iOS runners are included. With Flutter 3.44.0 on PATH, run
these checks from `mobile/`:

```powershell
.\setup.ps1
```

The setup script installs locked dependencies and runs `flutter analyze`
and `flutter test`.

For Android development, start the FastAPI backend and run:

```powershell
# Android emulator (backend on the Windows host)
flutter run --dart-define=CARBONX_API_BASE=http://10.0.2.2:8000

# Physical Android phone: bind FastAPI to the LAN and use the computer's IP.
flutter run --dart-define=CARBONX_API_BASE=http://192.168.1.10:8000
```

The Android debug runner allows local HTTP. Use HTTPS for release builds
and configure your distribution signing before publishing. iOS builds
require macOS and Xcode.

```powershell
flutter build apk --release --dart-define=CARBONX_API_BASE=https://api.example.com
```

## Included journeys

- Phone OTP and labelled demo login
- Persistent JWT session and `/me` refresh
- Farmer farm/credit dashboard
- Marketplace browsing with fallback-data disclosure
- Wallet split summary and transaction history
- Trust/validation status
- Profile and logout

The mobile client never connects directly to Supabase and uses the same backend
access-control boundary as the web application.
