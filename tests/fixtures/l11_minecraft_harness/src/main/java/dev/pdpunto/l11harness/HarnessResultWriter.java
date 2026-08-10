package dev.pdpunto.l11harness;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

final class HarnessResultWriter {
    private HarnessResultWriter() {
    }

    static void writeAtomically(Path resultPath, HarnessResult result) throws IOException {
        Path parent = resultPath.getParent();
        if (parent != null) {
            Files.createDirectories(parent);
        }
        Path temp = Files.createTempFile(parent, resultPath.getFileName().toString(), ".tmp");
        try {
            Files.writeString(temp, result.toJson(), StandardCharsets.UTF_8);
            try {
                Files.move(temp, resultPath, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException ex) {
                Files.move(temp, resultPath, StandardCopyOption.REPLACE_EXISTING);
            }
        } finally {
            Files.deleteIfExists(temp);
        }
    }
}
