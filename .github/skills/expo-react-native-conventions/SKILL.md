---
name: expo-react-native-conventions
description: Project structure, navigation, auth flow, API client patterns, and state management conventions for the Expo/React Native frontend.
---

# Expo + React Native Conventions

## When to Use

Use this skill when scaffolding the frontend, adding screens, wiring navigation, implementing auth, building the API client, or managing client-side state.

## Project Expectations

- Frontend lives in `frontend/` at the repo root.
- TypeScript only. Do not add plain JS files to the frontend.
- Use **Expo SDK** with the TypeScript template (`npx create-expo-app frontend --template`).
- Use **expo-router** (file-based routing) for all navigation. Do not add react-navigation separately.
- **Target iOS, Android, and web.** Build mobile-first but web-compatible from the start.

### Web Compatibility Rules

These rules apply to every file in the frontend. Violating them makes web support painful to retrofit.

1. **No bare `Platform.OS === 'ios'` or `'android'` branches** without a `'web'` fallback in the same conditional.
2. **No native-only libraries** without a verified web fallback. Check Expo compatibility table before adding any package.
3. **No `expo-secure-store` called directly.** Use the cross-platform storage abstraction described in the Auth Flow section below.
4. **No `TouchableNativeFeedback` or other platform-only primitives.** Use `Pressable` everywhere.
5. Test the web target periodically with `npx expo start --web`. Do not let web diverge silently over many PRs.

## Directory Structure

```
frontend/
├── app/                    # expo-router file-based routes
│   ├── (auth)/             # AuthStack: login, register screens
│   ├── (app)/              # AppStack: home, lobby, game, cards, profile
│   │   ├── _layout.tsx     # Tab navigator or stack root
│   │   └── ...
│   └── _layout.tsx         # Root layout; guards based on auth state
├── src/
│   ├── api/                # API client, interceptors, per-domain request functions
│   ├── store/              # Zustand stores (auth, room, game)
│   ├── hooks/              # Custom hooks (useAuth, useRoom, useGame, useWebSocket)
│   ├── components/         # Shared UI components
│   └── constants/          # Colors, layout, event name strings
├── assets/                 # Images, fonts, icons
└── app.json
```

## State Management

**Decision**: Use **Zustand** for all shared client state. Do not use Redux.

- One store per domain: `authStore`, `roomStore`, `gameStore`.
- Keep stores flat; avoid deeply nested state.
- Co-locate selectors as named exports from the store file.
- Async actions (API calls) live in the store as actions, not in hooks or components.
- Derive UI state from store values; do not duplicate it.

## Auth Flow

### Cross-Platform Token Storage

`expo-secure-store` is not available on web. Create a storage abstraction at `src/utils/secureStorage.ts`:

```ts
import { Platform } from 'react-native';
import * as SecureStore from 'expo-secure-store';

export const secureStorage = {
  async get(key: string): Promise<string | null> {
    if (Platform.OS === 'web') return sessionStorage.getItem(key);
    return SecureStore.getItemAsync(key);
  },
  async set(key: string, value: string): Promise<void> {
    if (Platform.OS === 'web') { sessionStorage.setItem(key, value); return; }
    await SecureStore.setItemAsync(key, value);
  },
  async delete(key: string): Promise<void> {
    if (Platform.OS === 'web') { sessionStorage.removeItem(key); return; }
    await SecureStore.deleteItemAsync(key);
  },
};
```

- **Always import `secureStorage` from this module.** Never call `SecureStore` or `sessionStorage` directly in components or stores.
- On web, `sessionStorage` clears on tab close, which is acceptable for a game session. Do not use `localStorage` for tokens.
- On app launch, read tokens via `secureStorage.get`; restore auth state into `authStore`.
- Axios interceptors handle:
  1. Attach `Authorization: Bearer <access_token>` on every request.
  2. On 401 response → call `POST /auth/refresh` → retry original request once.
  3. On second 401 (refresh failed) → clear tokens and redirect to login.
- Root `_layout.tsx` gates AppStack from unauthenticated access using `authStore`.

## API Client

- Single axios instance created in `src/api/client.ts`.
- Base URL read from `EXPO_PUBLIC_API_URL` environment variable (set in `.env` at `frontend/`).
- Do not hardcode `localhost`; use the env var to point at the compose-hosted backend.
- Per-domain request files export typed async functions (e.g. `src/api/rooms.ts`, `src/api/auth.ts`).
- All API functions return typed data, not raw axios responses. Unwrap `.data` before returning.

## Forms

- Use **react-hook-form** with **zod** for all forms (login, register, create room, join room).
- Define the zod schema first, derive the TypeScript type from it, then wire into `useForm`.
- Show field-level validation errors inline, not as alerts.

## Navigation

- expo-router file-based routes are the source of truth for screen structure.
- Use `router.replace` for auth transitions (login → home, logout → login) to prevent back-navigation to auth screens.
- Use `router.push` for forward navigation within the app.
- Pass minimal data via route params; load full data inside the screen using the store or a hook.

## Styling

- Use React Native `StyleSheet.create` for component-level styles. No inline style objects on JSX.
- Keep a `constants/colors.ts` file for all color values. No hardcoded hex codes in component files.
- Plan for dark-mode from the start; use `useColorScheme` where color depends on theme.
- Avoid shadows using `shadowColor`/`shadowOffset` (iOS-only). Use `boxShadow` via a `Platform.select` if shadows are needed, or skip them.
- Navigation gestures (swipe-back) do not exist on web; expo-router degrades gracefully but do not design UX that depends on them.

## Phase 4 Checklist (Foundation)

Before Phase 5 work begins, confirm all of these:

- [ ] `npx create-expo-app frontend --template` completed.
- [ ] expo-router configured as the navigation system.
- [ ] AuthStack (login, register) renders and validates with react-hook-form + zod.
- [ ] `secureStorage` abstraction created and used everywhere tokens are touched.
- [ ] Axios instance created with base URL from env var.
- [ ] Auto-refresh interceptor implemented.
- [ ] `authStore` (Zustand) created and guards AppStack.
- [ ] App runs on iOS simulator, Android emulator, **and** `npx expo start --web` without errors.
- [ ] Frontend `.env` documented in repo README or docs.

## Expected Validation

- Mobile: `npx expo start` from `frontend/`, open in iOS simulator or Android emulator.
- Web dev: `npx expo start --web`.
- Web production build: `npx expo export --platform web` → outputs to `frontend/dist/`. Serve with any static file server to verify.
- For automation, use **jest + @testing-library/react-native** for unit and component tests.
- Do not test implementation details; test what the user sees and can interact with.
- Backend must be running via `docker compose up` for any integration flows.

## Web Production Compose Service (Phase 7)

When deploying, the web build becomes a static bundle that can be served from a container:

```yaml
# docker-compose.yml addition (Phase 7)
frontend:
  image: nginx:alpine
  volumes:
    - ./frontend/dist:/usr/share/nginx/html:ro
  ports:
    - "3000:80"
  depends_on:
    - backend
```

Do not add this until Phase 7. During development, run web via `npx expo start --web` on the host.
