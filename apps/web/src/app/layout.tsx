import { ClerkProvider } from "@clerk/nextjs";
import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import type { ReactNode } from "react";

import { DemoBanner } from "@/components/demo-banner";
import { CLERK_ENABLED } from "@/lib/auth-config";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Contable IA",
  description: "Document AI contable para pymes colombianas",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  const content: ReactNode = (
    <>
      <DemoBanner />
      {children}
    </>
  );
  return (
    <html lang="es" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        {/* ClerkProvider va dentro de <body> (Clerk Core 3). Sin clave: modo desarrollo. */}
        {CLERK_ENABLED ? (
          <ClerkProvider signInUrl="/sign-in" signUpUrl="/sign-up">
            {content}
          </ClerkProvider>
        ) : (
          content
        )}
      </body>
    </html>
  );
}
