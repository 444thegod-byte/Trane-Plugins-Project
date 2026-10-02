#include "../plugin/PluginEditor.h"
#include "../plugin/PluginProcessor.h"

#include <cmath>
#include <iostream>
#include <memory>
#include <stdexcept>

namespace {
int checks = 0;
void expect(bool condition, const juce::String& message) {
    ++checks;
    if (!condition) throw std::runtime_error(message.toStdString());
}
void near(float a, float b, const juce::String& message) {
    expect(std::abs(a - b) < 0.002f, message + " actual=" + juce::String(a) + " expected=" + juce::String(b));
}

struct Gestures : juce::AudioProcessorParameter::Listener {
    int starts = 0, ends = 0, depth = 0;
    void parameterValueChanged(int, float) override {}
    void parameterGestureChanged(int, bool starting) override {
        if (starting) { ++starts; ++depth; } else { ++ends; --depth; }
        expect(depth >= 0 && depth <= 1, "automation gestures must not nest or underflow");
    }
};

struct Fixture {
    trane::TraneAudioProcessor processor;
    std::unique_ptr<trane::TraneAudioProcessorEditor> editor;
    trane::panel::PanelState state;
    trane::panel::InspectorLayout layout;
    explicit Fixture(int index, float value = 0.4f, float scale = 1.0f) {
        processor.apvts.getParameter(trane::panel::controlAt(index).id)->setValueNotifyingHost(value);
        for (int i = 0; i < trane::panel::controlCount(); ++i)
            state.value[i] = processor.apvts.getParameter(trane::panel::controlAt(i).id)->getValue();
        layout = trane::panel::buildInspector(state);
        editor = std::make_unique<trane::TraneAudioProcessorEditor>(processor);
        editor->setSize(juce::roundToInt(1440 * scale), juce::roundToInt(720 * scale));
    }
    juce::AudioProcessorParameter* param(int index) { return processor.apvts.getParameter(trane::panel::controlAt(index).id); }
    juce::Point<float> point(int index, float fraction = 0.4f) {
        const int row = layout.controlRow[index];
        const auto& r = layout.row[row];
        const auto& col = layout.column[r.column];
        return {col.x + trane::panel::geom::kBlockPadX + col.labelW + trane::panel::geom::kGap + col.trackW * fraction, r.mid};
    }
    float width(int index) { return layout.column[layout.row[layout.controlRow[index]].column].trackW; }
    juce::MouseEvent event(juce::Point<float> position, juce::Point<float> down,
                           int modifiers = juce::ModifierKeys::leftButtonModifier, bool dragged = false) {
        const float scale = editor->getWidth() / 1440.0f;
        const auto now = juce::Time::getCurrentTime();
        return {juce::Desktop::getInstance().getMainMouseSource(), position * scale,
                juce::ModifierKeys(modifiers), 1.0f, 0, 0, 0, 0, editor.get(), editor.get(),
                now, down * scale, now, 1, dragged};
    }
    void down(juce::Point<float> p, int mods = juce::ModifierKeys::leftButtonModifier) { editor->mouseDown(event(p,p,mods)); }
    void drag(juce::Point<float> p, juce::Point<float> start, int mods = juce::ModifierKeys::leftButtonModifier) { editor->mouseDrag(event(p,start,mods,true)); }
    void up(juce::Point<float> p, juce::Point<float> start) { editor->mouseUp(event(p,start,0)); }
    void click(juce::Point<float> p) { down(p); up(p,p); }
};

int indexOf(const char* id) {
    for (int i = 0; i < trane::panel::controlCount(); ++i)
        if (juce::String(trane::panel::controlAt(i).id) == id) return i;
    throw std::runtime_error("missing control");
}

void testDirections() {
    int bars = 0, knobs = 0;
    for (int i = 0; i < trane::panel::controlCount(); ++i) {
        if (trane::panel::controlSlot(i) < 0 || trane::panel::controlAt(i).fmt == trane::panel::Fmt::Choice) continue;
        const bool knob = trane::panel::isKnob(i);
        knob ? ++knobs : ++bars;
        for (float scale : {0.6f, 1.0f, 1.5f}) {
            Fixture f(i,0.4f,scale);
            const auto p = f.point(i);
            const float before = f.param(i)->getValue();
            f.editor->mouseMove(f.event(p,p,0));
            expect(f.editor->getMouseCursor() == (knob ? juce::MouseCursor::UpDownResizeCursor : juce::MouseCursor::LeftRightResizeCursor), "cursor must match control shape");
            Gestures gestures;
            f.param(i)->addListener(&gestures);
            f.down(p);
            const auto orthogonal = knob ? p.translated(10,0) : p.translated(0,-10);
            f.drag(orthogonal,p);
            near(f.param(i)->getValue(),before,"wrong-axis drag must leave value unchanged");
            const auto positive = knob ? orthogonal.translated(0,-20) : orthogonal.translated(f.width(i)*0.1f,0);
            f.drag(positive,p);
            expect(f.param(i)->getValue() > before,"drawn-axis drag must increase value: " + juce::String(trane::panel::controlAt(i).id));
            f.drag(orthogonal,p);
            near(f.param(i)->getValue(),before,"returning pointer must restore starting value");
            f.up(orthogonal,p);
            expect(gestures.starts==1 && gestures.ends==1 && gestures.depth==0,"drag must be one balanced automation gesture");
            f.param(i)->removeListener(&gestures);
        }
    }
    expect(bars==20 && knobs==20,"all 40 continuous controls were exercised");
}

void testPrecisionAndLimits() {
    const int i=indexOf("ruin_drive");
    Fixture f(i);
    const auto p=f.point(i);
    const float before=f.param(i)->getValue(), amount=f.width(i)*0.1f;
    f.down(p);
    f.drag(p.translated(amount,0),p);
    const float coarse=f.param(i)->getValue();
    near(coarse,before+0.1f,"bar full range follows visible track width");
    f.drag(p.translated(amount,0),p,juce::ModifierKeys::leftButtonModifier|juce::ModifierKeys::shiftModifier);
    near(f.param(i)->getValue(),coarse,"adding Shift at fixed pointer must not jump");
    f.drag(p.translated(2*amount,0),p,juce::ModifierKeys::leftButtonModifier|juce::ModifierKeys::shiftModifier);
    near(f.param(i)->getValue(),coarse+0.02f,"Shift must provide five-times finer drag");
    f.drag(p.translated(3*amount,0),p,juce::ModifierKeys::leftButtonModifier|juce::ModifierKeys::ctrlModifier);
    near(f.param(i)->getValue(),coarse+0.025f,"Ctrl must provide twenty-times finer drag");
    f.drag(p.translated(1000,0),p);
    near(f.param(i)->getValue(),1,"drag clamps at upper endpoint");
    f.drag(p.translated(990,0),p);
    expect(f.param(i)->getValue()<1,"reversing at endpoint responds immediately");
    f.up(p.translated(990,0),p);
    f.click(f.point(i,0.75f));
    near(f.param(i)->getValue(),0.75f,"click visible horizontal track selects its location");
    f.editor->mouseDoubleClick(f.event(f.point(i),f.point(i),0));
    near(f.param(i)->getValue(),f.param(i)->getDefaultValue(),"double-click restores default");
}

void testChoiceAndSwitches() {
    const int choice=indexOf("sweep_mode");
    Fixture f(choice,0);
    for (int n : {2,0,1,1}) {
        const auto p=f.point(choice,(n+0.5f)/3.0f);
        f.editor->mouseMove(f.event(p,p,0));
        expect(f.editor->getMouseCursor()==juce::MouseCursor::PointingHandCursor,"segmented buttons use hand cursor");
        f.click(p);
        near(f.param(choice)->getValue(),n/2.0f,"click selects clicked LP/BP/HP segment");
    }
    auto p=f.point(choice,0.5f);
    f.down(p); f.drag(p.translated(0,-40),p); f.up(p.translated(0,-40),p);
    near(f.param(choice)->getValue(),0.5f,"dragging selector does not choose another option");
    juce::MouseWheelDetails wheel{};
    wheel.deltaX=1; wheel.deltaY=0;
    f.editor->mouseWheelMove(f.event(p,p,0),wheel);
    near(f.param(choice)->getValue(),0.5f,"horizontal-only wheel must not lower choice");
    f.editor->keyPressed(juce::KeyPress(juce::KeyPress::rightKey));
    f.editor->keyPressed(juce::KeyPress(juce::KeyPress::rightKey));
    near(f.param(choice)->getValue(),1,"choice arrows stop at HP instead of wrapping");

    for (int i=0; i<trane::panel::controlCount(); ++i) {
        if(trane::panel::controlSlot(i)>=0) continue;
        Fixture button(i,0);
        const auto& row=button.layout.row[button.layout.nodeTitleRow[trane::panel::controlNode(i)]];
        const auto& col=button.layout.column[row.column];
        const juce::Point<float> at{col.x+30,row.mid};
        button.down(at); button.drag(at.translated(20,0),at); button.up(at.translated(20,0),at);
        near(button.param(i)->getValue(),0,"dragging a module title must not toggle it");
        button.down(at,juce::ModifierKeys::rightButtonModifier); button.up(at,at);
        near(button.param(i)->getValue(),0,"right-click must not toggle module");
        button.click(at); near(button.param(i)->getValue(),1,"click enables module");
        button.click(at); near(button.param(i)->getValue(),0,"rapid repeated click still works");
    }
    for (const char* module : {"ruin","space","out"}) {
        const int i=indexOf(juce::String(module)=="ruin"?"ruin_drive":juce::String(module)=="space"?"space_mix":"output");
        const auto& row=f.layout.row[f.layout.nodeTitleRow[trane::panel::controlNode(i)]];
        const auto& col=f.layout.column[row.column];
        const juce::Point<float> at{col.x+30,row.mid};
        f.editor->mouseMove(f.event(at,at,0));
        expect(f.editor->getMouseCursor()==juce::MouseCursor::NormalCursor,"inert headers must not advertise dragging");
        f.param(i)->setValueNotifyingHost(0.9f);
        f.editor->mouseDoubleClick(f.event(at,at,0));
        near(f.param(i)->getValue(),f.param(i)->getDefaultValue(),"headers without switches still reset their module on double-click");
    }
}

void testAutomationLifetime() {
    const int i=indexOf("ruin_drive");
    Fixture f(i);
    Gestures gestures;
    f.param(i)->addListener(&gestures);
    const auto p=f.point(i);
    f.click(p);
    const int before=gestures.starts;
    f.editor->keyPressed(juce::KeyPress(juce::KeyPress::rightKey));
    expect(gestures.starts==before+1 && gestures.starts==gestures.ends,"keyboard change must notify balanced automation gesture");
    f.down(p);
    expect(gestures.depth==1,"mouse down opens gesture");
    f.editor.reset();
    expect(gestures.depth==0 && gestures.starts==gestures.ends,"closing editor during drag ends gesture");
    f.param(i)->removeListener(&gestures);
}
}

int main() {
    juce::ScopedJuceInitialiser_GUI gui;
    try {
        testDirections();
        testPrecisionAndLimits();
        testChoiceAndSwitches();
        testAutomationLifetime();
        std::cout << "PASS: " << checks << " editor interaction checks\n";
        return 0;
    } catch(const std::exception& e) {
        std::cerr << "FAIL: " << e.what() << " after " << checks << " checks\n";
        return 1;
    }
}
