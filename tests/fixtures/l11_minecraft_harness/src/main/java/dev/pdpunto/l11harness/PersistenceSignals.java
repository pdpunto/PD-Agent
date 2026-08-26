package dev.pdpunto.l11harness;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.AtomicMoveNotSupportedException;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

import com.google.gson.JsonObject;

final class PersistenceSignals {
    private static final Map<String, String> SIGNALS = new LinkedHashMap<>();
    private static Path evidencePath;

    private PersistenceSignals() {
    }

    static synchronized void configure(String phase, String scenarioId, String worldId, Path path) {
        evidencePath = path.toAbsolutePath().normalize();
        SIGNALS.clear();
        SIGNALS.put("phase", phase);
        SIGNALS.put("scenario_id", scenarioId);
        SIGNALS.put("world_id", worldId);
        SIGNALS.put("process_id", Long.toString(ProcessHandle.current().pid()));
        write();
    }

    static synchronized void mark(String name) {
        if (evidencePath == null) {
            return;
        }
        SIGNALS.put(name.toLowerCase(), Instant.now().toString());
        write();
    }

    static synchronized boolean has(String name) {
        return SIGNALS.containsKey(name.toLowerCase());
    }

    static boolean await(String name, long timeoutMillis) {
        long deadline = System.currentTimeMillis() + Math.max(timeoutMillis, 1000L);
        while (System.currentTimeMillis() < deadline) {
            if (has(name)) {
                return true;
            }
            try {
                Thread.sleep(25L);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return false;
            }
        }
        return has(name);
    }

    private static void write() {
        try {
            Path parent = evidencePath.getParent();
            if (parent != null) {
                Files.createDirectories(parent);
            }
            JsonObject object = new JsonObject();
            SIGNALS.forEach(object::addProperty);
            Path temp = evidencePath.resolveSibling(evidencePath.getFileName() + ".tmp");
            Files.writeString(temp, object.toString(), StandardCharsets.UTF_8);
            try {
                Files.move(temp, evidencePath, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
            } catch (AtomicMoveNotSupportedException ex) {
                Files.move(temp, evidencePath, StandardCopyOption.REPLACE_EXISTING);
            }
        } catch (IOException ex) {
            throw new IllegalStateException("failed to persist persistence lifecycle evidence", ex);
        }
    }
}
