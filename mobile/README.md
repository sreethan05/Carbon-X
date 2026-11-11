# CarbonX Mobile

Flutter Material 3 client for the existing CarbonX FastAPI backend.

## First-time platform setup

Flutter is not installed on the machine where this source was created. After
installing Flutter 3.24+ run this once from `mobile/`:

```powershell
.\setup.ps1
```

The setup script generates version-matched Android/iOS runners, installs
dependencies, formats the source, and runs `flutter analyze` plus `flutter test`.

The command generates native Android/iOS runners while retaining `lib/` and
`pubspec.yaml`. Then run:

```powershell
# Android emulator (backend on the Windows host)
flutter run --dart-define=CARBONX_API_BASE=http://10.0.2.2:8000

# Physical phone on the same Wi-Fi: replace with the computer's LAN IP
flutter run --dart-define=CARBONX_API_BASE=http://192.168.1.10:8000
```

For a production build, use the deployed HTTPS backend URL:

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
