import { createContext } from "react";
import type { User } from "./types";

export interface AuthState {
  user: User | null;
  loading: boolean; // true while we check if somebody is already logged in
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthState | null>(null);