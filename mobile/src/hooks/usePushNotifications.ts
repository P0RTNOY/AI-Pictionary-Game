import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { useCallback, useEffect, useRef, useState } from "react";
import { AppState } from "react-native";

import { registerDeviceToken, unregisterDeviceToken } from "../api/deviceTokens";
import { captureError } from "../utils/errorReporter";


Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldPlaySound: false,
    shouldSetBadge: true,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});


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
  const registrationGeneration = useRef(0);
  const registeredDevice = useRef<{ userId: string; token: string } | null>(null);
  const activeRegistrationWork = useRef<Promise<void> | null>(null);

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
    if (activeRegistrationWork.current) return activeRegistrationWork.current;
    const generation = ++registrationGeneration.current;
    const work = (async () => {
      try {
        const result = await register(userId);
        if (registrationGeneration.current !== generation) {
          if (result.token) {
            try {
              await unregisterDeviceToken(result.token);
            } catch (error) {
              captureError(error, { area: "stale_push_unregistration", userId });
            }
          }
          return;
        }
        setPermissionStatus(result.permissionStatus);
        setRegistered(Boolean(result.token));
        setTokenFingerprint(result.tokenFingerprint);
        registeredDevice.current = result.token ? { userId, token: result.token } : null;
        setRegistrationError(null);
      } catch (error) {
        if (registrationGeneration.current !== generation) return;
        captureError(error, { area: "push_registration" });
        setRegistered(false);
        setTokenFingerprint(null);
        setRegistrationError(error instanceof Error ? error.message : "Push registration failed");
      }
    })();
    activeRegistrationWork.current = work;
    return work.finally(() => {
      if (activeRegistrationWork.current === work) activeRegistrationWork.current = null;
    });
  }, [enabled, userId]);

  useEffect(() => {
    registrationGeneration.current += 1;
    registeredDevice.current = null;
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
    const current = registeredDevice.current;
    registrationGeneration.current += 1;
    const pendingRegistration = activeRegistrationWork.current;
    if (pendingRegistration) await pendingRegistration;
    if (!current) return;
    try {
      await unregisterDeviceToken(current.token);
    } catch (error) {
      captureError(error, { area: "push_unregistration", userId: current.userId });
    } finally {
      if (registeredDevice.current === current) {
        registeredDevice.current = null;
        setRegistered(false);
        setTokenFingerprint(null);
      }
    }
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
