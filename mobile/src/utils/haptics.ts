import * as Haptics from "expo-haptics";

export async function tapHaptic() {
  try {
    await Haptics.selectionAsync();
  } catch {
    // Haptics are optional on simulators, web, and some Android devices.
  }
}

export async function successHaptic() {
  try {
    await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
  } catch {
    // Optional feedback.
  }
}

export async function warningHaptic() {
  try {
    await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
  } catch {
    // Optional feedback.
  }
}
