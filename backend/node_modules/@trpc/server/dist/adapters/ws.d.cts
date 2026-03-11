import "../index.d-BiUz7kM_.cjs";
import { AnyRouter, BaseHandlerOptions, CreateContextCallback, MaybePromise, inferRouterContext } from "../unstable-core-do-not-import.d-DEjy79nN.cjs";
import "../index.d-CvZXeEyR.cjs";
import { NodeHTTPCreateContextFnOptions } from "../index.d-rTzuWy5s.cjs";
import { IncomingMessage } from "http";
import ws from "ws";

//#region src/adapters/wsEncoder.d.ts

/**
 * Encoder for WebSocket wire format.
 * Encodes outgoing messages and decodes incoming messages.
 *
 * @example
 * ```ts
 * const customEncoder: Encoder = {
 *   encode: (data) => myFormat.stringify(data),
 *   decode: (data) => myFormat.parse(data),
 * };
 * ```
 */
interface Encoder {
  /** Encode data for transmission over the wire */
  encode(data: unknown): string | Uint8Array;
  /** Decode data received from the wire */
  decode(data: string | ArrayBuffer | Uint8Array): unknown;
}
/**
 * Default JSON encoder - used when no encoder is specified.
 * This maintains backwards compatibility with existing behavior.
 */
declare const jsonEncoder: Encoder;
//# sourceMappingURL=wsEncoder.d.ts.map
//#endregion
//#region src/adapters/ws.d.ts
/**
 * @public
 */
type CreateWSSContextFnOptions = NodeHTTPCreateContextFnOptions<IncomingMessage, ws.WebSocket>;
/**
 * @public
 */
type CreateWSSContextFn<TRouter extends AnyRouter> = (opts: CreateWSSContextFnOptions) => MaybePromise<inferRouterContext<TRouter>>;
type WSConnectionHandlerOptions<TRouter extends AnyRouter> = BaseHandlerOptions<TRouter, IncomingMessage> & CreateContextCallback<inferRouterContext<TRouter>, CreateWSSContextFn<TRouter>>;
/**
 * Web socket server handler
 */
type WSSHandlerOptions<TRouter extends AnyRouter> = WSConnectionHandlerOptions<TRouter> & {
  wss: ws.WebSocketServer;
  prefix?: string;
  keepAlive?: {
    /**
     * Enable heartbeat messages
     * @default false
     */
    enabled: boolean;
    /**
     * Heartbeat interval in milliseconds
     * @default 30_000
     */
    pingMs?: number;
    /**
     * Terminate the WebSocket if no pong is received after this many milliseconds
     * @default 5_000
     */
    pongWaitMs?: number;
  };
  /**
   * Disable responding to ping messages from the client
   * **Not recommended** - this is mainly used for testing
   * @default false
   */
  dangerouslyDisablePong?: boolean;
  /**
   * Custom encoder for wire encoding (e.g. custom binary formats)
   * @default jsonEncoder
   */
  experimental_encoder?: Encoder;
};
declare function getWSConnectionHandler<TRouter extends AnyRouter>(opts: WSSHandlerOptions<TRouter>): (client: ws.WebSocket, req: IncomingMessage) => void;
/**
 * Handle WebSocket keep-alive messages
 */
declare function handleKeepAlive(client: ws.WebSocket, pingMs?: number, pongWaitMs?: number): void;
declare function applyWSSHandler<TRouter extends AnyRouter>(opts: WSSHandlerOptions<TRouter>): {
  broadcastReconnectNotification: () => void;
};
//#endregion
export { CreateWSSContextFn, CreateWSSContextFnOptions, Encoder, WSConnectionHandlerOptions, WSSHandlerOptions, applyWSSHandler, getWSConnectionHandler, handleKeepAlive, jsonEncoder };
//# sourceMappingURL=ws.d.cts.map