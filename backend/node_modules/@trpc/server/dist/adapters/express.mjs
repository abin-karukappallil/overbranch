import { __toESM, require_objectSpread2 } from "../getErrorShape-vC8mUXJD.mjs";
import { run } from "../codes-DagpWZLc.mjs";
import "../tracked-Bjtgv3wJ.mjs";
import "../parseTRPCMessage-CTow-umk.mjs";
import "../resolveResponse-BLZa62-J.mjs";
import "../contentTypeParsers-SN4WL9ze.mjs";
import "../unstable-core-do-not-import-9NNw8uQM.mjs";
import "../observable-UMO3vUa_.mjs";
import "../initTRPC-RoZMIBeA.mjs";
import { internal_exceptionHandler, nodeHTTPRequestHandler } from "../node-http-DHiQq80-.mjs";

//#region src/adapters/express.ts
var import_objectSpread2 = __toESM(require_objectSpread2(), 1);
function createExpressMiddleware(opts) {
	return (req, res) => {
		let path = "";
		run(async () => {
			path = req.path.slice(req.path.lastIndexOf("/") + 1);
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
export { createExpressMiddleware };
//# sourceMappingURL=express.mjs.map