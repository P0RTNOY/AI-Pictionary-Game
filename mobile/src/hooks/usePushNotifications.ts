import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AppState } from "react-native";

import { registerDeviceToken, unregisterDeviceToken } from "../api/deviceTokens";
import { createIdentityWorkCoordinator, type IdentityWorkCoordinator } from "../identityWorkCoordinator";
import { runWithDeadline, settleWithin } from "../promiseDeadline";
import { captureError } from "../utils/errorReporter";


Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldPlaySound: false,
    shouldSetBadge: true,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

const PUSH_OPERATION_TIMEOUT_MS = 5_000;
const PUSH_COORDINATOR_TIMEOUT_MS = 30_000;
let nextPushSessionKey = 0;

type PushSession = {
  key: string;
  identity: string;
  credential: string;
};

type PushRegistrationResult = Awaited<ReturnType<typeof register>>;

export function usePushNotifications(
  userId: string | null,
  accessToken: string | null,
  onOpenGame: (gameId: string) => void,
  enabled = true,
) {
  const [permissionStatus, setPermissionStatus] = useState<string>("unknown");
  const [registered, setRegistered] = useState(false);
  const [tokenFingerprint, setTokenFingerprint] = useState<string | null>(null);
  const [registrationError, setRegistrationError] = useState<string | null>(null);
  const lastRouteKey = useRef<string | null>(null);
  const currentSession = useMemo<PushSession | null>(
    () => userId && accessToken
      ? { key: `${userId}:${++nextPushSessionKey}`, identity: userId, credential: accessToken }
      : null,
    [accessToken, userId],
  );
  const credentialSession = useRef<PushSession | null>(currentSession);
  const previousSession = useRef<PushSession | null>(null);
  const coordinator = useRef<IdentityWorkCoordinator<PushSession, PushRegistrationResult> | null>(null);
  credentialSession.current = currentSession;
  if (!coordinator.current) {
    coordinator.current = createIdentityWorkCoordinator<PushSession, PushRegistrationResult>({
      sessionKey: (session) => session.key,
      run: register,
      cleanup: async (session, result) => {
        const token = result.token;
        if (!token) return;
        try {
          const settlement = await runWithDeadline(
            (signal) => unregisterDeviceToken(token, session.credential, signal),
            PUSH_OPERATION_TIMEOUT_MS,
          );
          if (settlement.status === "timeout") throw new Error("Push unregistration timed out");
        } catch (error) {
          captureError(error, { area: "push_unregistration", userId: session.identity });
          throw error;
        }
      },
      accept: (_session, result) => {
        setPermissionStatus(result.permissionStatus);
        setRegistered(Boolean(result.token));
        setTokenFingerprint(result.tokenFingerprint);
        setRegistrationError(null);
      },
      reject: (session, error) => {
        captureError(error, { area: "push_registration", userId: session.identity });
        setRegistered(false);
        setTokenFingerprint(null);
        setRegistrationError(error instanceof Error ? error.message : "Push registration failed");
      },
      settle: (promise) => settleWithin(promise, PUSH_COORDINATOR_TIMEOUT_MS),
    });
  }

  const routeNotification = useCallback(
    (response: Notifications.NotificationResponse | null) => {
      if (!enabled) return;
      const data = response?.notification.request.content.data;
      const gameId = data?.game_id;
      if (typeof gameId !== "string") return;
      const routeKey = `${response?.notification.request.identifier ?? "notification"}:${gameId}`;
      if (lastRouteKey.current === routeKey) return;
      lastRouteKey.current = routeKey;
      onOpenGame(gameId);
    },
    [enabled, onOpenGame],
  );

  const refreshRegistration = useCallback(() => {
    if (!currentSession || !enabled) return Promise.resolve();
    return coordinator.current!.activate(currentSession);
  }, [currentSession, enabled]);

  useEffect(() => {
    const retiredSession = previousSession.current;
    previousSession.current = currentSession;
    if (retiredSession && (retiredSession.key !== currentSession?.key || !enabled)) {
      void coordinator.current!.retire(retiredSession);
    }
    lastRouteKey.current = null;
    setRegistered(false);
    setTokenFingerprint(null);
    setRegistrationError(null);
    if (!currentSession || !enabled) setPermissionStatus("unknown");
  }, [currentSession, enabled]);

  useEffect(() => {
    void refreshRegistration();
  }, [refreshRegistration]);

  useEffect(() => {
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") void refreshRegistration();
    });
    return () => subscription.remove();
  }, [refreshRegistration]);

  useEffect(() => {
    Notifications.getLastNotificationResponseAsync()
      .then(routeNotification)
      .catch(() => {
        // Notification cold-start routing is best-effort.
      });
  }, [routeNotification]);

  useEffect(() => {
    const subscription = Notifications.addNotificationResponseReceivedListener((response) => {
      routeNotification(response);
    });
    return () => subscription.remove();
  }, [routeNotification]);

  const unregisterCurrentToken = useCallback(async () => {
    const session = credentialSession.current;
    if (!session) return;
    await coordinator.current!.retire(session);
    setRegistered(false);
    setTokenFingerprint(null);
  }, []);

  return {
    permissionStatus,
    registered,
    tokenFingerprint,
    registrationError,
    refreshRegistration,
    unregisterCurrentToken,
  };
}


async function register(session: PushSession) {
  if (!Device.isDevice) return { permissionStatus: "simulator", token: null, tokenFingerprint: null };
  const existing = await requireWithin(
    Notifications.getPermissionsAsync(),
    "Checking notification permission timed out",
  );
  let status = existing.status;
  if (status !== "granted") {
    const requested = await requireWithin(
      Notifications.requestPermissionsAsync(),
      "Requesting notification permission timed out",
    );
    status = requested.status;
  }
  if (status !== "granted") return { permissionStatus: status, token: null, tokenFingerprint: null };

  const projectId = Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId;
  const expoToken = await requireWithin(
    projectId
      ? Notifications.getExpoPushTokenAsync({ projectId })
      : Notifications.getExpoPushTokenAsync(),
    "Push token acquisition timed out",
  );
  const token = expoToken.data;
  const registration = await runWithDeadline(
    (signal) => registerDeviceToken(token, session.credential, signal),
    PUSH_OPERATION_TIMEOUT_MS,
  );
  if (registration.status === "timeout") {
    try {
      await runWithDeadline(
        (signal) => unregisterDeviceToken(token, session.credential, signal),
        PUSH_OPERATION_TIMEOUT_MS,
      );
    } catch {
      // A timed-out registration is followed by bounded, best-effort cleanup.
    }
    throw new Error("Push registration timed out");
  }
  return {
    permissionStatus: status,
    token,
    tokenFingerprint: registration.value.token_fingerprint,
  };
}

async function requireWithin<Value>(promise: Promise<Value>, timeoutMessage: string): Promise<Value> {
  const settlement = await settleWithin(promise, PUSH_OPERATION_TIMEOUT_MS);
  if (settlement.status === "timeout") throw new Error(timeoutMessage);
  return settlement.value;
}
