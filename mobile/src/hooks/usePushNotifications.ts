import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { useCallback, useEffect, useRef, useState } from "react";
import { AppState } from "react-native";

import { registerDeviceToken } from "../api/deviceTokens";
import { captureError } from "../utils/errorReporter";


Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldPlaySound: false,
    shouldSetBadge: true,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});


export function usePushNotifications(userId: string | null, onOpenGame: (gameId: string) => void) {
  const [permissionStatus, setPermissionStatus] = useState<string>("unknown");
  const [registeredToken, setRegisteredToken] = useState<string | null>(null);
  const [registrationError, setRegistrationError] = useState<string | null>(null);
  const lastRouteKey = useRef<string | null>(null);

  const routeNotification = useCallback(
    (response: Notifications.NotificationResponse | null) => {
      const data = response?.notification.request.content.data;
      const gameId = data?.game_id;
      if (typeof gameId !== "string") return;
      const routeKey = `${response?.notification.request.identifier ?? "notification"}:${gameId}`;
      if (lastRouteKey.current === routeKey) return;
      lastRouteKey.current = routeKey;
      onOpenGame(gameId);
    },
    [onOpenGame],
  );

  const refreshRegistration = useCallback(async () => {
    if (!userId) return;
    register(userId)
      .then((result) => {
        setPermissionStatus(result.permissionStatus);
        setRegisteredToken(result.token);
        setRegistrationError(null);
      })
      .catch((error) => {
        captureError(error, { area: "push_registration" });
        setRegistrationError(error instanceof Error ? error.message : "Push registration failed");
      });
  }, [userId]);

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

  return { permissionStatus, registeredToken, registrationError, refreshRegistration };
}


async function register(userId: string) {
  if (!Device.isDevice) return { permissionStatus: "simulator", token: null };
  const existing = await Notifications.getPermissionsAsync();
  let status = existing.status;
  if (status !== "granted") {
    const requested = await Notifications.requestPermissionsAsync();
    status = requested.status;
  }
  if (status !== "granted") return { permissionStatus: status, token: null };

  const projectId = Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId;
  const token = projectId
    ? (await Notifications.getExpoPushTokenAsync({ projectId })).data
    : (await Notifications.getExpoPushTokenAsync()).data;
  await registerDeviceToken(token);
  return { permissionStatus: status, token };
}
