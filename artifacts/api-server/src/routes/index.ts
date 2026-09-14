import { Router, type IRouter } from "express";
import healthRouter from "./health";
import skyguardRouter from "./skyguard";

const router: IRouter = Router();

router.use(healthRouter);
router.use(skyguardRouter);

export default router;
