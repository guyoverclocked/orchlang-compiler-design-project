CXX ?= c++
CPPFLAGS := -Iinclude
CXXFLAGS ?= -std=c++17 -Wall -Wextra -pedantic -O2
DEPFLAGS := -MMD -MP

BUILD_DIR := build
CORE_SOURCES := src/diagnostic.cpp src/ast.cpp src/lexer.cpp src/parser.cpp src/symbol_table.cpp src/tokenizer_contracts.cpp src/sha256.cpp src/semantic_analyzer.cpp src/cost_analyzer.cpp src/ir.cpp src/certificate.cpp src/relational.cpp src/relational_baselines.cpp src/interpreter.cpp
CORE_OBJECTS := $(CORE_SOURCES:src/%.cpp=$(BUILD_DIR)/%.o)
MAIN_OBJECT := $(BUILD_DIR)/main.o
TEST_OBJECT := $(BUILD_DIR)/tests.o
DEPS := $(CORE_OBJECTS:.o=.d) $(MAIN_OBJECT:.o=.d) $(TEST_OBJECT:.o=.d)

.PHONY: all check test examples sanitize clean proofs

all: orchc

orchc: $(CORE_OBJECTS) $(MAIN_OBJECT)
	$(CXX) $(CXXFLAGS) $^ -o $@

orchlang_tests: $(CORE_OBJECTS) $(TEST_OBJECT)
	$(CXX) $(CXXFLAGS) $^ -o $@

$(BUILD_DIR)/%.o: src/%.cpp
	@mkdir -p $(BUILD_DIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(DEPFLAGS) -c $< -o $@

$(BUILD_DIR)/tests.o: tests/tests.cpp
	@mkdir -p $(BUILD_DIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(DEPFLAGS) -c $< -o $@

test: orchlang_tests
	./orchlang_tests

examples: orchc
	@set -e; for file in examples/valid/*.orch examples/boundary/zero_budget.orch examples/boundary/long_identifier.orch examples/boundary/retry_one.orch examples/boundary/empty_branch.orch; do ./orchc check "$$file" >/dev/null; done
	@set -e; for file in examples/invalid/*.orch examples/boundary/empty_workflow.orch; do if ./orchc check "$$file" >/dev/null 2>&1; then echo "expected invalid source to fail: $$file"; exit 1; fi; done
	@set -e; for file in examples/valid/*.orch; do ./orchc certify "$$file" >/dev/null; done
	@echo "examples: valid corpus accepted, invalid corpus rejected, certificates emitted"

check: all test examples

sanitize:
	$(MAKE) clean
	$(MAKE) CXXFLAGS='-std=c++17 -Wall -Wextra -pedantic -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer' check

# The Coq development (Coq 8.18; not needed by `check`).  Prints the axioms
# each main theorem depends on, which must be none.
proofs:
	coqc -Q proofs OrchLang proofs/OrchLang.v
	coqc -Q proofs OrchLang proofs/Assumptions.v

clean:
	rm -rf $(BUILD_DIR) orchc orchlang_tests
	rm -f proofs/*.vo proofs/*.vok proofs/*.vos proofs/*.glob proofs/.*.aux .lia.cache

-include $(DEPS)
