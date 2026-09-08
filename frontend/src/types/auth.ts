export type Role = "engineer" | "supervisor" | "collector";

export type AuthenticatedUser = {
  username: string;
  display_name: string;
  role: Role;
};

export type AccessToken = {
  access_token: string;
  token_type: string;
  user: AuthenticatedUser;
};

// Seed credentials defined on the backend in app/auth.py.
// Used for one-click operator switching in the prototype demo.
export const DEMO_OPERATORS: {
  username: string;
  name: string;
  role: Role;
  password: string;
  badge: string;
}[] = [
  {
    username: "nadia.k",
    name: "Nadia Karim",
    role: "engineer",
    password: "engineer-dev-password",
    badge: "Engineer",
  },
  {
    username: "sam.o",
    name: "Sam Okafor",
    role: "supervisor",
    password: "supervisor-dev-password",
    badge: "Supervisor",
  },
];
