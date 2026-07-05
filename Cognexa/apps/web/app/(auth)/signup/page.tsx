"use client";

/**
 * apps/web/app/(auth)/signup/page.tsx
 *
 * NEW FILE — fixes issue #6 (Frontend Authentication UX): "Currently only
 * Login exists." Mirrors the visual style of app/(auth)/login/page.tsx.
 * Always registers as Engineer (see apps/api/schemas/auth.py /
 * routers/auth.py — role is intentionally not client-controlled).
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { motion } from "framer-motion";
import toast from "react-hot-toast";
import { Loader2, Zap } from "lucide-react";
import api from "@/lib/api";
import { useAuthStore } from "@/store/auth";

const signupSchema = z.object({
  full_name: z.string().min(1, "Full name is required"),
  email: z.string().email("Valid email required"),
  password: z.string().min(8, "Password must be at least 8 characters"),
});

type SignupForm = z.infer<typeof signupSchema>;

export default function SignupPage() {
  const router = useRouter();
  const login = useAuthStore((s) => s.login);
  const [isLoading, setIsLoading] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<SignupForm>({ resolver: zodResolver(signupSchema) });

  const onSubmit = async (data: SignupForm) => {
    setIsLoading(true);
    try {
      await api.post("/auth/signup", data);
      // Auto-login right after signup for a smooth first-run experience.
      await login(data.email, data.password);
      toast.success("Account created — welcome to INDUS MIND!");
      router.push("/dashboard");
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Could not create account";
      toast.error(msg);
    } finally {
      setIsLoading(false);
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
          <span className="font-bold text-lg">INDUS MIND</span>
        </div>

        <h1 className="text-2xl font-bold mb-1 text-center">Create your account</h1>
        <p className="text-muted-foreground mb-8 text-center">
          New accounts start with Engineer access. An admin can grant more later.
        </p>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
          <div>
            <label className="block text-sm font-medium mb-2">Full name</label>
            <input
              {...register("full_name")}
              type="text"
              autoComplete="name"
              placeholder="Jane Doe"
              className="w-full px-4 py-3 rounded-lg bg-secondary border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary transition"
            />
            {errors.full_name && (
              <p className="text-destructive text-xs mt-1">{errors.full_name.message}</p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">Email address</label>
            <input
              {...register("email")}
              type="email"
              autoComplete="email"
              placeholder="engineer@company.com"
              className="w-full px-4 py-3 rounded-lg bg-secondary border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary transition"
            />
            {errors.email && (
              <p className="text-destructive text-xs mt-1">{errors.email.message}</p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">Password</label>
            <input
              {...register("password")}
              type="password"
              autoComplete="new-password"
              placeholder="At least 8 characters"
              className="w-full px-4 py-3 rounded-lg bg-secondary border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary transition"
            />
            {errors.password && (
              <p className="text-destructive text-xs mt-1">{errors.password.message}</p>
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
                Creating account…
              </>
            ) : (
              "Create account"
            )}
          </button>
        </form>

        <p className="text-center text-sm text-muted-foreground mt-6">
          Already have an account?{" "}
          <Link href="/login" className="text-primary font-medium hover:underline">
            Sign in
          </Link>
        </p>
      </motion.div>
    </div>
  );
}
