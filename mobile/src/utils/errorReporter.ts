type ErrorContext = Record<string, unknown>;

export type ErrorReporter = {
  capture(error: unknown, context?: ErrorContext): void;
  message(message: string, context?: ErrorContext): void;
};

class ConsoleErrorReporter implements ErrorReporter {
  capture(error: unknown, context: ErrorContext = {}) {
    console.warn("[AI Pictionary]", context, error);
  }

  message(message: string, context: ErrorContext = {}) {
    console.warn("[AI Pictionary]", message, context);
  }
}

export const errorReporter: ErrorReporter = new ConsoleErrorReporter();

export function captureError(error: unknown, context?: ErrorContext) {
  errorReporter.capture(error, context);
}

export function captureMessage(message: string, context?: ErrorContext) {
  errorReporter.message(message, context);
}

// Future Sentry/Bugsnag integration can replace errorReporter here without
// changing gameplay code paths.
