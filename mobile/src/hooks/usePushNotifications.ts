import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { useCallback, useEffect, useRef, useState } from "react";
import { AppState } from "react-native";

import { registerDeviceToken, unregisterDeviceToken } from "../api/deviceTokens";
import { createIdentityWorkCoordinator, type IdentityWorkCoordinator } from "../identityWorkCoordinator";
import { captureError } from "../utils/errorReporter";


Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldPlaySound: false,
    shouldSetBadge: true,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

type PushRegistrationResult = Awaited<ReturnType<typeof register>>;

export function usePushNotifications(
  userId: string | null,
  onOpenGame: (gameId: string) => void,
  enabled = true,
) {
  const [permissionStatus, setPermissionStatus] = useState<string>("unknown");
  const [registered, setRegistered] = useState(false);
  const [tokenFingerprint, setTokenFingerprint] = useState<string | null>(null);
  const [registrationError, setRegistrationError] = useState<string | null>(null);
  const lastRouteKey = useRef<string | null>(null);
  const credentialIdentity = useRef<string | null>(userId);
  const previousIdentity = useRef<string | null>(null);
  const coordinator = useRef<IdentityWorkCoordinator<PushRegistrationResult> | null>(null);
  credentialIdentity.current = userId;
  if (!coordinator.current) {
    coordinator.current = createIdentityWorkCoordinator<PushRegistrationResult>({
      run: register,
      cleanup: async (identity, result) => {
        if (!result.token) return;
        try {
          await unregisterDeviceToken(result.token);
        } catch (error) {
          captureError(error, { area: "push_unregistration", userId: identity });
        }
      },
      canCleanup: (identity) => credentialIdentity.current === identity,
      accept: (_identity, result) => {
        setPermissionStatus(result.permissionStatus);
        setRegistered(Boolean(result.token));
        setTokenFingerprint(result.tokenFingerprint);
        setRegistrationError(null);
      },
      reject: (identity, error) => {
        captureError(error, { area: "push_registration", userId: identity });
        setRegistered(false);
        setTokenFingerprint(null);
        setRegistrationError(error instanceof Error ? error.message : "Push registration failed");
      },
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
    if (!userId || !enabled) return Promise.resolve();
    return coordinator.current!.activate(userId);
  }, [enabled, userId]);

  useEffect(() => {
    const retiredIdentity = previousIdentity.current;
    previousIdentity.current = userId;
    if (retiredIdentity && (retiredIdentity !== userId || !enabled)) {
      void coordinator.current!.retire(retiredIdentity);
    }
    lastRouteKey.current = null;
    setRegistered(false);
    setTokenFingerprint(null);
    setRegistrationError(null);
    if (!userId || !enabled) setPermissionStatus("unknown");
  }, [enabled, userId]);

  useEffect(() => {
    refreshRegistration();
  }, [refreshRegistration]);

  useEffect(() => {
    const subscription = AppState.addEventListener("change", (state) => {
      if (state === "active") refreshRegistration();
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
    const currentIdentity = credentialIdentity.current;
    if (!currentIdentity) return;
    await coordinator.current!.retire(currentIdentity);
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


async function register(userId: string) {
  if (!Device.isDevice) return { permissionStatus: "simulator", token: null, tokenFingerprint: null };
  const existing = await Notifications.getPermissionsAsync();
  let status = existing.status;
  if (status !== "granted") {
    const requested = await Notifications.requestPermissionsAsync();
    status = requested.status;
  }
  if (status !== "granted") return { permissionStatus: status, token: null, tokenFingerprint: null };

  const projectId = Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId;
  const token = projectId
    ? (await Notifications.getExpoPushTokenAsync({ projectId })).data
    : (await Notifications.getExpoPushTokenAsync()).data;
  const registered = await registerDeviceToken(token);
  return { permissionStatus: status, token, tokenFingerprint: registered.token_fingerprint };
}
