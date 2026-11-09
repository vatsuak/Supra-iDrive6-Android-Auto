// SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
// Exercise the production plugin callbacks against a fake native framework.
// The fake exports the real popup overload's symbol so dlsym is tested too.
#include <assert.h>
#include <map>
#include "../rhmiapp/nbt_aad_app.cpp"

namespace fake_prompt {
struct Event { unsigned id; bool hasValue, value; };
std::vector<Event> events;
std::vector<unsigned> actions;
void event(unsigned id, bool hasValue, bool value) {
    Event e = { id, hasValue, value }; events.push_back(e);
}
}

namespace bmw {
template <typename T> BasicString<T>::BasicString(const T* s) {
    size_t n = 0; while (s && s[n]) ++n;
    m_data = new T[n + 1];
    for (size_t i = 0; i < n; ++i) m_data[i] = s[i];
    m_data[n] = 0;
}
template <typename T> BasicString<T>::BasicString(const BasicString& s) {
    size_t n = 0; while (s.m_data[n]) ++n;
    m_data = new T[n + 1];
    for (size_t i = 0; i <= n; ++i) m_data[i] = s.m_data[i];
}
template <typename T> BasicString<T>::~BasicString() { delete[] m_data; }
template class BasicString<char>;
template class BasicString<unsigned short>;
Parcel::Parcel(bool value) { memset(m_storage, 0, sizeof(m_storage)); m_storage[0] = value ? 1 : 0; }
Parcel::~Parcel() {}
void Parcel::readBool(bool& value) const { value = m_storage[0] != 0; }
TextID::TextID(unsigned id) : m_id(id), m_type(0x28) {}
ImageID::ImageID(unsigned id) : m_id(id), m_type(0x2b) {}
Variant::~Variant() { delete m_obj; }
template <typename K, typename V> Map<K, V>::~Map() { delete reinterpret_cast<std::map<K, V>*>(m_table); }
template <typename K, typename V> V& Map<K, V>::operator[](const K& key) {
    if (!m_table) m_table = new std::map<K, V>;
    return (*reinterpret_cast<std::map<K, V>*>(m_table))[key];
}
template class Map<unsigned, Variant>;
DataTableBase::DataTableBase(Map<unsigned, Variant>*, unsigned) { memset(m_storage, 0, sizeof(m_storage)); }
PluginApp::PluginApp(IDispatcher&, BasicString<char>, unsigned, unsigned,
                     RHMIInterfaceVersion, const Bundle&, const Bundle&) { memset(m_storage, 0, sizeof(m_storage)); }
void PluginApp::addHandler(unsigned id, const ActionDelegate&) { fake_prompt::actions.push_back(id); }
void PluginApp::addHandler(unsigned, unsigned, const ActionDelegate&) {}
void PluginApp::triggerEvent(unsigned id) { fake_prompt::event(id, false, false); }
__attribute__((used, visibility("default")))
void PluginApp::triggerEvent(unsigned id, const Parcel& parcel) {
    bool value = false; parcel.readBool(value); fake_prompt::event(id, true, value);
    // Native events may call back synchronously; verify show/hide is reentrant.
    onPromptFocus(this, parcel);
}
void PluginApp::post(Runnable*, unsigned) {}
void PluginApp::updateModel(unsigned, const TextID&) {}
void PluginApp::updateModel(unsigned, const ImageID&) {}
void PluginApp::updateModel(unsigned, bool) {}
void PluginApp::updateModel(unsigned, const DataTableBase&) {}
void PluginApp::setProperty(unsigned, unsigned, const Parcel&) {}
void PluginApp::cdsAddPropertyChangedEventHandler(BasicString<char>&, unsigned, const CdsDelegate&) {}
bool PluginApp::onInit() { return true; }
void PluginApp::onFinalize() {}
} // namespace bmw

int main() {
    // These host tests must never launch the actual car daemon or a phone watcher.
    assert(access(kDaemon, F_OK) != 0 && access(kPromptFlag, F_OK) != 0);
    assert(!controlPortBusy());
    int dummy[4] = { 0 };
    bmw::PluginApp app(*reinterpret_cast<bmw::IDispatcher*>(dummy), bmw::BasicString<char>("NbtAad"), 1, 0,
        bmw::RHMI_INTERFACE_VERSION_1, *reinterpret_cast<bmw::Bundle*>(dummy), *reinterpret_cast<bmw::Bundle*>(dummy));
    assert(appOnInit(&app));
    for (unsigned action = 120; action <= 123; ++action) {
        bool registered = false;
        for (size_t i = 0; i < fake_prompt::actions.size(); ++i) registered |= fake_prompt::actions[i] == action;
        assert(registered);
    }
    bmw::Parcel yes(true), no(false);
    assert(!promptEnabled());
    DaemonState idle = readDaemonState();
    serviceConnectionPrompt(&app, idle);
    assert(g_phoneWatchPid == 0 && fake_prompt::events.empty()); // default-off path is inert
    onPromptTest(&app, no);
    assert(fake_prompt::events.empty()); // no popup until car state is known
    g_lastGear = 1; g_lastPdc = 0; g_promptCallKnown = true; g_promptNativeBusy = false;
    onPromptTest(&app, no);
    assert(!g_promptUnsupported && g_connectionPrompt.visible() && g_promptFocusSeen);
    assert(fake_prompt::events.size() == 1 && fake_prompt::events.back().id == 131);
    assert(fake_prompt::events.back().hasValue && fake_prompt::events.back().value);
    onPromptDismiss(&app, no);
    assert(!g_connectionPrompt.visible() && !fake_prompt::events.back().value);
    size_t count = fake_prompt::events.size();
    onPromptDismiss(&app, no); onPromptOpen(&app, no);
    assert(fake_prompt::events.size() == count); // duplicate callbacks are harmless

    onPromptTest(&app, no);
    onPromptFocus(&app, yes); onPromptFocus(&app, no);
    assert(!g_connectionPrompt.visible() && !fake_prompt::events.back().value); // BACK/native dismissal

    onPromptTest(&app, no);
    g_lastGear = kReverseGear; g_startTime = 0;
    onPromptOpen(&app, no);
    assert(!g_connectionPrompt.visible() && g_startTime == 0); // revalidate at click time
    g_lastGear = 1;

    g_connectionPrompt.reset();
    g_connectionPrompt.poll(0, true, true, true, false, false);
    assert(g_connectionPrompt.poll(2000, true, true, true, false, false) == nbt::ConnectionPrompt::SHOW);
    onPromptOpen(&app, no);
    assert(g_startTime == 0); // automatic Open needs a fresh sample from the spawned watcher

    onPromptTest(&app, no);
    onPromptOpen(&app, no);
    assert(g_startTime > 0 && g_entryStart);
    assert(fake_prompt::events.back().id == kEvOpenMenu && !fake_prompt::events.back().hasValue);
    assert(!g_connectionPrompt.visible() && g_phoneWatchPid == 0);
    appOnFinalize(&app);
    puts("production popup callbacks with fake framework and real symbol lookup: OK");
}
