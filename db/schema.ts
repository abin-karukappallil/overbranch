import { pgTable, text, timestamp, boolean, integer, jsonb } from "drizzle-orm/pg-core";

export const user = pgTable("user", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  email: text("email").notNull().unique(),
  emailVerified: boolean("email_verified").notNull().default(false),
  image: text("image"),
  role: text("role").default("user"),
  createdAt: timestamp("created_at").notNull().defaultNow(),
  updatedAt: timestamp("updated_at").notNull().defaultNow()
});

export const session = pgTable("session", {
  id: text("id").primaryKey(),
  expiresAt: timestamp("expires_at").notNull(),
  token: text("token").notNull().unique(),
  createdAt: timestamp("created_at").notNull().defaultNow(),
  updatedAt: timestamp("updated_at").notNull().defaultNow(),
  ipAddress: text("ip_address"),
  userAgent: text("user_agent"),
  userId: text("user_id").notNull().references(() => user.id, { onDelete: "cascade" })
});

export const account = pgTable("account", {
  id: text("id").primaryKey(),
  accountId: text("account_id").notNull(),
  providerId: text("provider_id").notNull(),
  userId: text("user_id").notNull().references(() => user.id, { onDelete: "cascade" }),
  accessToken: text("access_token"),
  refreshToken: text("refresh_token"),
  idToken: text("id_token"),
  accessTokenExpiresAt: timestamp("access_token_expires_at"),
  refreshTokenExpiresAt: timestamp("refresh_token_expires_at"),
  scope: text("scope"),
  password: text("password"),
  createdAt: timestamp("created_at").notNull().defaultNow(),
  updatedAt: timestamp("updated_at").notNull().defaultNow()
});

export const verification = pgTable("verification", {
  id: text("id").primaryKey(),
  identifier: text("identifier").notNull(),
  value: text("value").notNull(),
  expiresAt: timestamp("expires_at").notNull(),
  createdAt: timestamp("created_at").defaultNow(),
  updatedAt: timestamp("updated_at").defaultNow()
});

export const workspaces = pgTable("workspaces", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  slug: text("slug").notNull().unique(),
  avatarUrl: text("avatar_url"),
  plan: text("plan").notNull().default("pro"),
  ownerId: text("owner_id").notNull().references(() => user.id, { onDelete: "cascade" }),
  createdAt: timestamp("created_at").notNull().defaultNow(),
  updatedAt: timestamp("updated_at").notNull().defaultNow()
});

export const workspaceMembers = pgTable("workspace_members", {
  id: text("id").primaryKey(),
  workspaceId: text("workspace_id").notNull().references(() => workspaces.id, { onDelete: "cascade" }),
  userId: text("user_id").notNull().references(() => user.id, { onDelete: "cascade" }),
  role: text("role").notNull().default("member"),
  joinedAt: timestamp("joined_at").notNull().defaultNow()
});

export const workspaceInvitations = pgTable("workspace_invitations", {
  id: text("id").primaryKey(),
  workspaceId: text("workspace_id").notNull().references(() => workspaces.id, { onDelete: "cascade" }),
  email: text("email").notNull(),
  role: text("role").notNull().default("member"),
  status: text("status").notNull().default("pending"),
  createdAt: timestamp("created_at").notNull().defaultNow()
});

export const projects = pgTable("projects", {
  id: text("id").primaryKey(),
  workspaceId: text("workspace_id").notNull().references(() => workspaces.id, { onDelete: "cascade" }),
  name: text("name").notNull(),
  description: text("description"),
  repository: text("repository"),
  defaultBranch: text("default_branch").notNull().default("main"),
  language: text("language").notNull().default("latex"),
  status: text("status").notNull().default("active"),
  isPublic: boolean("is_public").notNull().default(false),
  isFavorite: boolean("is_favorite").notNull().default(false),
  template: text("template").notNull().default("IEEEtran"),
  starsCount: integer("stars_count").notNull().default(0),
  lastActiveAt: timestamp("last_active_at").notNull().defaultNow(),
  createdAt: timestamp("created_at").notNull().defaultNow(),
  updatedAt: timestamp("updated_at").notNull().defaultNow()
});

export const templates = pgTable("templates", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  category: text("category").notNull(),
  description: text("description").notNull(),
  fileExtension: text("file_extension").notNull().default("cls"),
  isFeatured: boolean("is_featured").notNull().default(false),
  usageCount: integer("usage_count").notNull().default(0),
  content: text("content")
});

export const userPreferences = pgTable("user_preferences", {
  id: text("id").primaryKey(),
  userId: text("user_id").notNull().unique().references(() => user.id, { onDelete: "cascade" }),
  theme: text("theme").notNull().default("dark"),
  emailNotifications: boolean("email_notifications").notNull().default(true),
  securityAlerts: boolean("security_alerts").notNull().default(true),
  updatedAt: timestamp("updated_at").notNull().defaultNow()
});

export const editorPreferences = pgTable("editor_preferences", {
  id: text("id").primaryKey(),
  userId: text("user_id").notNull().unique().references(() => user.id, { onDelete: "cascade" }),
  fontSize: integer("font_size").notNull().default(14),
  tabSize: integer("tab_size").notNull().default(2),
  wordWrap: boolean("word_wrap").notNull().default(true),
  autoCompile: boolean("auto_compile").notNull().default(true),
  engine: text("engine").notNull().default("pdfLaTeX"),
  lineNumbers: boolean("line_numbers").notNull().default(true)
});

export const notifications = pgTable("notifications", {
  id: text("id").primaryKey(),
  userId: text("user_id").notNull().references(() => user.id, { onDelete: "cascade" }),
  title: text("title").notNull(),
  message: text("message").notNull(),
  type: text("type").notNull().default("info"),
  isRead: boolean("is_read").notNull().default(false),
  createdAt: timestamp("created_at").notNull().defaultNow()
});

export const recentFiles = pgTable("recent_files", {
  id: text("id").primaryKey(),
  projectId: text("project_id").notNull().references(() => projects.id, { onDelete: "cascade" }),
  filePath: text("file_path").notNull(),
  fileName: text("file_name").notNull(),
  language: text("language").notNull().default("latex"),
  lastOpenedAt: timestamp("last_opened_at").notNull().defaultNow()
});

export const activityLogs = pgTable("activity_logs", {
  id: text("id").primaryKey(),
  workspaceId: text("workspace_id").notNull().references(() => workspaces.id, { onDelete: "cascade" }),
  userId: text("user_id").notNull().references(() => user.id, { onDelete: "cascade" }),
  action: text("action").notNull(),
  target: text("target").notNull(),
  metadata: jsonb("metadata"),
  createdAt: timestamp("created_at").notNull().defaultNow()
});

export type User = typeof user.$inferSelect;
export type Workspace = typeof workspaces.$inferSelect;
export type WorkspaceMember = typeof workspaceMembers.$inferSelect;
export type WorkspaceInvitation = typeof workspaceInvitations.$inferSelect;
export type Project = typeof projects.$inferSelect;
export type Template = typeof templates.$inferSelect;
export type UserPreferences = typeof userPreferences.$inferSelect;
export type EditorPreferences = typeof editorPreferences.$inferSelect;
export type Notification = typeof notifications.$inferSelect;
export type RecentFile = typeof recentFiles.$inferSelect;
export type ActivityLog = typeof activityLogs.$inferSelect;
