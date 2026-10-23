import "./globals.css";
import AppShell from "@/components/layout/AppShell";
import { APP_NAME, APP_TAGLINE } from "@/lib/constants";

export const metadata = {
  title: { default: APP_NAME, template: `%s · ${APP_NAME}` },
  description: APP_TAGLINE,
};

export const viewport = { width: "device-width", initialScale: 1, themeColor: "#12223a" };

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
