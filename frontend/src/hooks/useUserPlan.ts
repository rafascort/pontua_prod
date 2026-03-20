import { useAuth, getPlanDisplayName, getPlanLimit, getPageBalance } from "@/contexts/AuthContext";

export interface UserPlan {
  planName: string;
  pageBalance: number;
  pageLimit: number;
  extraPages: number;
  email: string;
  role: "user" | "admin";
  pageCount: number;
  planStatus: string;
  stripeCustomerId: string | null;
}

export function useUserPlan() {
  const { user, isLoading, refreshUser } = useAuth();

  const planStatus = user?.plan_status || "free";
  const pageCount = user?.page_count || 0;
  const pageLimit = getPlanLimit(planStatus);
  const pageBalance = getPageBalance(pageCount, planStatus);

  const plan: UserPlan = {
    planName: getPlanDisplayName(planStatus),
    pageBalance,
    pageLimit,
    extraPages: Math.max(0, pageCount - pageLimit),
    email: user?.email || "",
    role: (user?.role as "user" | "admin") || "user",
    pageCount,
    planStatus,
    stripeCustomerId: user?.stripe_customer_id || null,
  };

  const canConsume = (count: number) => pageBalance >= count;

  return { plan, isLoading, canConsume, refreshUser };
}
