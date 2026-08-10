-- Fix notifications table: migrate user_id → receiver_id and drop old column

-- Copy existing user_id data into receiver_id where receiver_id is null
UPDATE "notifications" SET "receiver_id" = "user_id" WHERE "receiver_id" IS NULL AND "user_id" IS NOT NULL;

-- Drop the NOT NULL constraint on user_id by recreating without it
-- (Postgres doesn't have a simple "DROP NOT NULL IF EXISTS" so we use ALTER)
ALTER TABLE "notifications" ALTER COLUMN "user_id" DROP NOT NULL;

-- Set default on user_id to avoid future issues  
ALTER TABLE "notifications" ALTER COLUMN "user_id" SET DEFAULT NULL;
