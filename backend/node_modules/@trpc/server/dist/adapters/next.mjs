import { __toESM, require_objectSpread2 } from "../getErrorShape-vC8mUXJD.mjs";
import { run } from "../codes-DagpWZLc.mjs";
import { TRPCError } from "../tracked-Bjtgv3wJ.mjs";
import "../parseTRPCMessage-CTow-umk.mjs";
import "../resolveResponse-BLZa62-J.mjs";
import "../contentTypeParsers-SN4WL9ze.mjs";
import "../unstable-core-do-not-import-9NNw8uQM.mjs";
import "../observable-UMO3vUa_.mjs";
import "../initTRPC-RoZMIBeA.mjs";
import { internal_exceptionHandler, nodeHTTPRequestHandler } from "../node-http-DHiQq80-.mjs";

//#region src/adapters/next.ts
var import_objectSpread2 = __toESM(require_objectSpread2(), 1);
function createNextApiHandler(opts) {
	return async (req, res) => {
		let path = "";
		await run(async () => {
			path = run(() => {
				if (typeof req.query["trpc"] === "string") return req.query["trpc"];
				if (Array.isArray(req.query["trpc"])) return req.query["trpc"].join("/");
				throw new TRPCError({
					message: "Query \"trpc\" not found - is the file named `[trpc]`.ts or `[...trpc].ts`?",
					code: "INTERNAL_SERVER_ERROR"
				});
			});
			await nodeHTTPRequestHandler((0, import_objectSpread2.default)((0, import_objectSpread2.default)({}, opts), {}, {
				req,
				res,
				path
			}));
		}).catch(internal_exceptionHandler((0, import_objectSpread2.default)({
			req,
			res,
			path
		}, opts)));
	};
}

//#endregion
export { createNextApiHandler };
//# sourceMappingURL=next.mjs.map