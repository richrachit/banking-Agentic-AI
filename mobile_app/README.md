# Banking Operations AI Mobile

An Expo SDK 57 client for the Banking Operations AI platform. One codebase runs on Android, iOS, tablets, and the web while the FastAPI service remains the system of record.

The app supports five role-scoped workspaces:

- Customer: register, apply for a loan, explicitly consent to a credit-bureau enquiry, upload each document type, track AI progression, view dormant accounts, and request reactivation.
- Loan Operations: review applications, inspect evidence and AI progression, upload supporting evidence, and run the exception agent.
- Credit Manager: review credit-deviation approvals and record an accountable decision.
- Compliance: manage dormant-account and transfer approvals.
- Administrator: view all operational queues and the governed AI model registry.

The customer never enters a CIBIL/credit score. The mobile app sends PAN plus recorded consent to the API; the configured provider retrieves the result, and the backend policy agent decides whether the case continues, needs human review, or is declined. Application IDs are generated only by the backend repository.

## Prerequisites

- Node.js 22.13 or newer (the minimum for Expo SDK 57)
- The repository Python virtual environment and FastAPI dependencies
- Android Studio/emulator or an Android device for Android testing
- macOS with Xcode for a local iOS Simulator; on Windows, use a physical iPhone with Expo Go or an EAS cloud build

## Start the API

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m uvicorn banking_agents.api_app:app --host 0.0.0.0 --port 8001
```

The API exposes health at `http://127.0.0.1:8001/api/v1/health` and interactive documentation at `http://127.0.0.1:8001/docs`.

## Configure the client

For Android Emulator, no `.env` file is needed: the app defaults to `http://10.0.2.2:8001`. iOS Simulator and web default to `http://127.0.0.1:8001`.

For a physical device, copy `.env.example` to `.env` and replace the example with the computer's LAN address:

```powershell
Copy-Item .env.example .env
```

The phone and computer must be on the same trusted network. The local firewall must allow port 8001. Do not expose this demonstration API to the public internet.

## Install and run

```powershell
cd mobile_app
npm install
npx expo start
```

Then press `a` for Android, `i` for iOS on macOS, `w` for web, or scan the Expo Go QR code on a physical device.

Direct scripts are also available:

```powershell
npm run android
npm run ios
npm run web
```

Expo Go development does not require an Expo account. When signed Android/iOS artifacts are needed, `eas.json` provides internal development/preview profiles and a store-ready production profile:

```powershell
npx eas-cli build --platform all --profile preview
npx eas-cli build --platform all --profile production
```

EAS cloud builds require an Expo account and the appropriate Apple/Google signing setup.

## Validation

```powershell
npm run typecheck
npm run lint
npm run doctor
```

## Architecture

```text
src/app/                 Expo Router screens
src/components/          Responsive design system and authenticated shell
src/context/auth.tsx     Session lifecycle and role identity
src/lib/api.ts           Typed API envelope/error handling and platform URL
src/lib/storage.ts       SecureStore on Android/iOS; browser storage fallback
src/lib/types.ts         Shared client-side API data contracts
```

Authentication tokens use encrypted SecureStore on Android and iOS. Browser storage is an explicit development fallback and does not offer equivalent protection. DocumentPicker opens only after a user action, copies a native file to cache for immediate upload, and sends multipart data without persisting document contents in client state.

## Current demonstration boundaries

- Authentication tokens live in API memory and are invalidated when the API restarts.
- JSON/SQLite persistence and local bureau fixtures are for development, not production banking.
- Production needs the bank identity provider with MFA, PostgreSQL, object storage, malware scanning, TLS, certificate controls, mobile attestation, and approved bureau/KYC integrations.
- Synthetic training metrics are not evidence of production accuracy. The admin registry makes dataset provenance and lifecycle state visible.
- iOS binaries cannot be compiled locally on Windows; use macOS/Xcode or EAS Build.
