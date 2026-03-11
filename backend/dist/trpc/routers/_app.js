"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.appRouter = void 0;
const init_1 = require("../init");
const latexRouter_1 = require("./latexRouter");
exports.appRouter = (0, init_1.router)({
    latex: latexRouter_1.latexRouter,
});
