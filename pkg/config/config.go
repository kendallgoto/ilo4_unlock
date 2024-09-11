//  This file is part of ilo4_unlock (https://github.com/kendallgoto/ilo4_unlock/).
//  Copyright (c) 2024 Kendall Goto.
//
//  This program is free software: you can redistribute it and/or modify
//  it under the terms of the GNU General Public License as published by
//  the Free Software Foundation, version 3.
//
//  This program is distributed in the hope that it will be useful, but
//  WITHOUT ANY WARRANTY; without even the implied warranty of
//  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
//  General Public License for more details.
//
//  You should have received a copy of the GNU General Public License
//  along with this program. If not, see <http://www.gnu.org/licenses/>.

package config

import (
	"embed"
	"encoding/hex"
	"fmt"
	"net/url"
	"os"
	"path"
	"reflect"
	"regexp"

	"github.com/mitchellh/mapstructure"
	"golang.org/x/exp/slices"

	"github.com/spf13/viper"
)

type PatchConfigs struct {
	Default string
	Patches map[string]PatchDef
}
type PatchDef struct {
	Description string
	BinaryInfo  struct {
		Name string
		Url  url.URL
	} `mapstructure:"binary"`
	Checksums struct {
		Binary []byte
		Result []byte
	} `mapstructure:"checksum"`
	BootloaderPatches []PatchSegment `mapstructure:"bootloader"`
	KernelPatches     []PatchSegment `mapstructure:"kernel"`
	UserlandPatches   []PatchSegment `mapstructure:"userland"`
}
type PatchSegment struct {
	Remark       string
	Offset       uint32
	Size         uint32
	PreviousData []byte `mapstructure:"prev_data"`
	PatchData    []byte `mapstructure:"patch"`
}

var Default string
var Patches map[string]PatchDef

func extendedDecodeHook() mapstructure.DecodeHookFuncType {
	return func(
		f reflect.Type,
		t reflect.Type,
		data interface{},
	) (interface{}, error) {
		if f.Kind() != reflect.String {
			return data, nil
		}

		if t == reflect.TypeOf([]byte{}) {
			str := data.(string)
			whitespace := regexp.MustCompile(`\s`)
			return hex.DecodeString(whitespace.ReplaceAllString(str, ""))
		}
		if t == reflect.TypeOf(url.URL{}) {
			return url.Parse(data.(string))
		}
		return data, nil
	}
}

func BuildConfig(embeddedConf embed.FS, additionalConfig []string) error {
	viper.SetConfigType("yaml")
	f, err := embeddedConf.Open("patches/config.yml")
	if err != nil {
		return err
	}
	defer f.Close()

	viper.ReadConfig(f)
	patchDefs := viper.GetStringSlice("include")
	patchDefs = append(patchDefs, additionalConfig...)
	Patches = map[string]PatchDef{}
	for _, patchName := range patchDefs {
		patchPath := path.Join(patchName, "patch.yml")
		f, err = embeddedConf.Open(patchPath)
		if err != nil {
			if !slices.Contains(additionalConfig, patchName) {
				return err
			}
			f, err = os.Open(patchPath)
			if err != nil {
				return err
			}
		}
		defer f.Close()
		nestedConfig := viper.New()
		nestedConfig.SetConfigType("yaml")
		nestedConfig.ReadConfig(f)

		var patch PatchDef
		err := nestedConfig.Unmarshal(&patch, viper.DecodeHook(extendedDecodeHook()))
		if err != nil {
			return err
		}
		cleanName := path.Base(path.Dir(patchPath))
		if _, exists := Patches[cleanName]; exists {
			return fmt.Errorf("patch with name %s already exists", cleanName)
		}
		Patches[cleanName] = patch
		if patchName == viper.GetString("default") {
			Default = cleanName
		}
	}
	return nil
}
