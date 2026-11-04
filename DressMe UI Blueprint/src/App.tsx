import { useState } from "react";
import Sidebar from "./features/shell/Sidebar";
import ShopTabs from "./features/shell/ShopTabs";
import { isShopPage, type Page } from "./features/shell/navigation";
import HelpMePack from "./features/helpmepack/HelpMePack";
import { AuthProvider, useAuth } from "./features/auth/AuthProvider";
import AuthScreen from "./features/auth/AuthScreen";
import Onboarding from "./features/onboarding/Onboarding";
import { Alert, FullScreenLoader } from "./features/profile/FormControls";
import { useUserData, UserDataProvider } from "./features/profile/UserDataProvider";
import StyleProfile from "./features/profile/StyleProfile";
import Settings from "./features/settings/Settings";
import DashboardPage from "./features/dashboard/DashboardPage";
import FindSimilarPage from "./features/purchase/FindSimilarPage";
import ShopNotifications from "./features/shop/ShopNotifications";
import ShouldIBuyPage from "./features/purchase/ShouldIBuyPage";
import StylistPage from "./features/stylist/StylistPage";
import AvatarPage from "./features/avatar/AvatarPage";
import WardrobePage from "./features/wardrobe/WardrobePage";
import { WardrobeProvider } from "./features/wardrobe/WardrobeProvider";
import { getSupabaseConfigMessage } from "./lib/supabase";
import WardrobeGapsPage from "./features/wardrobegaps/WardrobeGapsPage";

function ConfigScreen({ message }: { message: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#FAF9F6] px-6">
      <div className="w-full max-w-lg rounded-2xl border border-[#E2E0D8] bg-white p-8">
        <div className="flex items-baseline gap-1">
          <span className="font-display text-2xl font-semibold italic text-[#1C1C1C]">Dress</span>
          <span className="font-display text-2xl font-semibold text-[#556B2F]">Me</span>
        </div>
        <h1 className="mt-5 font-display text-2xl font-semibold text-[#1C1C1C]">
          Configuration required
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-[#8C8A82]">{message}</p>
        <p className="mt-4 rounded-lg bg-[#F0EFEA] p-3 text-xs leading-relaxed text-[#8C8A82]">
          Add the variables to <span className="font-mono">DressMe UI Blueprint/.env</span> and
          restart the dev server. Only the public anon key belongs in the frontend.
        </p>
      </div>
    </div>
  );
}

function AuthenticatedApp() {
  const { signOut } = useAuth();
  const { profile, loading, error, refresh } = useUserData();
  const [page, setPage] = useState<Page>("dashboard");
  const [setupDismissed, setSetupDismissed] = useState(false);
  const [addSignal, setAddSignal] = useState(0);

  const goTo = (next: Page) => {
    setPage(next);
    document.querySelector("main")?.scrollTo({ top: 0 });
  };

  const renderPage = () => {
    switch (page) {
      case "dashboard": return <DashboardPage onNavigate={goTo} />;
      case "wardrobe": return <WardrobePage addSignal={addSignal} />;
      case "wardrobe-gaps": return <WardrobeGapsPage />;
      case "help-me-pack": return <HelpMePack onOpenWardrobe={() => goTo("wardrobe")} />;
      case "should-i-buy": return <ShouldIBuyPage />;
      case "ai-stylist": return <StylistPage />;
      case "avatar": return <AvatarPage />;
      case "style-profile": return <StyleProfile />;
      case "find-similar": return <FindSimilarPage onOpenAvatar={() => goTo("avatar")} />;
      case "settings": return <Settings />;
    }
  };

  if (loading) {
    return <FullScreenLoader label="Loading your DressMe profile..." />;
  }

  if (error || !profile) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#FAF9F6] px-6">
        <div className="w-full max-w-lg space-y-4">
          <Alert>
            {error ?? "We could not load your profile. Please try again."}
          </Alert>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => void refresh()}
              className="rounded-lg bg-[#556B2F] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#6B8A3A]"
            >
              Try again
            </button>
            <button
              type="button"
              onClick={() => void signOut()}
              className="rounded-lg border border-[#E2E0D8] bg-white px-5 py-2.5 text-sm font-semibold text-[#1C1C1C] hover:bg-[#F0EFEA]"
            >
              Sign out
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!profile.onboarding_completed && !setupDismissed) {
    return (
      <Onboarding
        onComplete={() => {
          setSetupDismissed(true);
          setPage("dashboard");
        }}
        onSkip={() => {
          setSetupDismissed(true);
        }}
      />
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-[#FAF9F6]">
      <Sidebar
        current={page}
        onNav={goTo}
        onAddItem={() => {
          goTo("wardrobe");
          setAddSignal((count) => count + 1);
        }}
      />
      <main className="ml-[260px] flex-1 overflow-y-auto">
        <div className="p-10 max-w-[1200px]">
          <WardrobeProvider>
          {!profile.onboarding_completed && (
            <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#556B2F]/20 bg-[#E8EDE0] px-5 py-4">
              <div>
                <p className="text-sm font-semibold text-[#1C1C1C]">Finish your style profile</p>
                <p className="mt-0.5 text-xs text-[#556B2F]">
                  Add your fit and style preferences so recommendations match you.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSetupDismissed(false)}
                className="rounded-lg bg-[#556B2F] px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-[#6B8A3A]"
              >
                Complete profile setup
              </button>
            </div>
          )}
          {isShopPage(page) && <ShopTabs current={page} onNav={goTo} />}
          {renderPage()}
          <ShopNotifications onOpen={() => goTo("dashboard")} />
          </WardrobeProvider>
        </div>
      </main>
    </div>
  );
}

function AppShell() {
  const { user, loading } = useAuth();
  const configMessage = getSupabaseConfigMessage();

  if (configMessage) return <ConfigScreen message={configMessage} />;
  if (loading) return <FullScreenLoader label="Checking your session..." />;
  if (!user) return <AuthScreen />;

  return (
    <UserDataProvider>
      <AuthenticatedApp />
    </UserDataProvider>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}
