import { createClient } from "@supabase/supabase-js";

/**
 * Server-side Supabase client using the service role key.
 * Used exclusively in tRPC mutation handlers to broadcast realtime events
 * after DB writes (the DB-write-then-broadcast pattern from spec sections 5, 8, 10).
 *
 * NEVER expose this client or the service role key to the browser.
 */

const supabaseUrl = process.env.SUPABASE_URL!;
const supabaseServiceKey = process.env.SUPABASE_SERVICE_ROLE_KEY!;

if (!supabaseUrl || !supabaseServiceKey) {
  console.warn(
    "[lib/supabase] SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set. " +
    "Server-side realtime broadcasts will not work."
  );
}

export const supabaseAdmin = createClient(supabaseUrl, supabaseServiceKey, {
  auth: {
    autoRefreshToken: false,
    persistSession: false,
  },
});

/**
 * Broadcast a realtime event on a Supabase channel from the server side.
 * Used after tRPC mutations to push updates to subscribed clients.
 *
 * @param channelName - e.g. "project:{uuid}" or "document:{uuid}"
 * @param event - e.g. "chat.message", "comment.created", "project.file.created"
 * @param payload - the event payload to broadcast
 */
export async function serverBroadcast(
  channelName: string,
  event: string,
  payload: Record<string, unknown>
) {
  const channel = supabaseAdmin.channel(channelName);

  await channel.send({
    type: "broadcast",
    event,
    payload,
  });

  // Clean up the channel after sending — server doesn't need to stay subscribed
  await supabaseAdmin.removeChannel(channel);
}
