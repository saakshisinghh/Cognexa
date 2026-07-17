"use client";

/**
 * apps/web/app/(auth)/forgot-password/page.tsx
 *
 * NEW FILE — fixes issue #6 (Frontend Authentication UX): "Need Forgot
 * Password." Calls POST /api/v1/auth/forgot-password (added in
 * apps/api/routers/auth.py). That endpoint always returns success to avoid
 * leaking which emails are registered, so the UI always shows the same
 * confirmation message regardless of outcome.
 */

import { useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { motion } from "framer-motion";
import { Loader2, Zap, MailCheck } from "lucide-react";
import api from "@/lib/api";

const forgotSchema = z.object({
  email: z.string().email("Valid email required"),
});

type ForgotForm = z.infer<typeof forgotSchema>;

export default function ForgotPasswordPage() {
  const [isLoading, setIsLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ForgotForm>({ resolver: zodResolver(forgotSchema) });

  const onSubmit = async (data: ForgotForm) => {
    setIsLoading(true);
    try {
      await api.post("/auth/forgot-password", data);
    } catch {
      // Intentionally ignored — the endpoint always responds the same way
      // whether or not the email exists, to avoid account enumeration.
    } finally {
      setIsLoading(false);
      setSubmitted(true);
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-8">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="w-full max-w-md"
      >
        <div className="flex items-center gap-2 mb-8 justify-center">
          <div className="w-8 h-8 indus-gradient rounded-lg flex items-center justify-center">
            <Zap className="w-4 h-4 text-white" />
          </div>
          <span className="font-bold text-lg">Cognexa</span>
        </div>

        {submitted ? (
          <div className="text-center">
            <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-4">
              <MailCheck className="w-6 h-6 text-primary" />
            </div>
            <h1 className="text-xl font-bold mb-2">Check your email</h1>
            <p className="text-muted-foreground text-sm mb-8">
              If an account exists for that email, we've sent a link to reset your password.
              It expires in 1 hour.
            </p>
            <Link href="/login" className="text-primary font-medium text-sm hover:underline">
              Back to sign in
            </Link>
          </div>
        ) : (
          <>
            <h1 className="text-2xl font-bold mb-1 text-center">Forgot your password?</h1>
            <p className="text-muted-foreground mb-8 text-center">
              Enter your email and we'll send you a reset link.
            </p>

            <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
              <div>
                <label className="block text-sm font-medium mb-2">Email address</label>
                <input
                  {...register("email")}
                  type="email"
                  autoComplete="email"
                  placeholder="you@company.com"
                  className="w-full px-4 py-3 rounded-lg bg-secondary border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary transition"
                />
                {errors.email && (
                  <p className="text-destructive text-xs mt-1">{errors.email.message}</p>
                )}
              </div>

              <button
                type="submit"
                disabled={isLoading}
                className="w-full py-3 rounded-lg indus-gradient text-white font-semibold flex items-center justify-center gap-2 hover:opacity-90 active:opacity-80 transition disabled:opacity-50"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Sending…
                  </>
                ) : (
                  "Send reset link"
                )}
              </button>
            </form>

            <p className="text-center text-sm text-muted-foreground mt-6">
              Remembered it?{" "}
              <Link href="/login" className="text-primary font-medium hover:underline">
                Back to sign in
              </Link>
            </p>
          </>
        )}
      </motion.div>
    </div>
  );
}