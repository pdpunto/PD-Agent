package dev.pdpunto.l11harness;

import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

import net.minecraft.server.world.ServerWorld;
import net.minecraft.util.math.BlockPos;

final class TargetBridge {
    private static final String CONTRACT_METHOD = "applyProbeState";

    private TargetBridge() {
    }

    static boolean applyProbeState(String targetEntrypointClass, ServerWorld world, BlockPos pos) {
        Class<?> targetClass = resolveTargetClass(targetEntrypointClass);
        Method method = resolveContractMethod(targetClass);
        try {
            Object result = method.invoke(null, world, pos);
            if (result instanceof Boolean value) {
                return value.booleanValue();
            }
            throw new IllegalStateException("target bridge returned non-boolean result: " + targetClass.getName());
        } catch (ReflectiveOperationException exc) {
            throw new IllegalStateException("failed to invoke target bridge: " + targetClass.getName(), exc);
        }
    }

    private static Class<?> resolveTargetClass(String targetEntrypointClass) {
        if (targetEntrypointClass == null || targetEntrypointClass.trim().isEmpty()) {
            throw new IllegalArgumentException("missing target entrypoint class");
        }
        try {
            return Class.forName(targetEntrypointClass.trim());
        } catch (ClassNotFoundException exc) {
            throw new IllegalStateException("target entrypoint class not found: " + targetEntrypointClass, exc);
        }
    }

    private static Method resolveContractMethod(Class<?> targetClass) {
        Method method;
        try {
            method = targetClass.getDeclaredMethod(CONTRACT_METHOD, ServerWorld.class, BlockPos.class);
        } catch (NoSuchMethodException exc) {
            throw new IllegalStateException("target bridge method missing: " + targetClass.getName() + "#" + CONTRACT_METHOD, exc);
        }
        int modifiers = method.getModifiers();
        if (!Modifier.isPublic(modifiers) || !Modifier.isStatic(modifiers)) {
            throw new IllegalStateException("target bridge method must be public static: " + targetClass.getName() + "#" + CONTRACT_METHOD);
        }
        if (method.getReturnType() != boolean.class) {
            throw new IllegalStateException("target bridge method must return boolean: " + targetClass.getName() + "#" + CONTRACT_METHOD);
        }
        Class<?>[] parameterTypes = method.getParameterTypes();
        if (parameterTypes.length != 2 || parameterTypes[0] != ServerWorld.class || parameterTypes[1] != BlockPos.class) {
            throw new IllegalStateException("target bridge method signature mismatch: " + targetClass.getName() + "#" + CONTRACT_METHOD);
        }
        return method;
    }
}
