import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SwadesAI Voice Agent",
  description: "Conversational voice agent with live monitoring and warm transfer",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
