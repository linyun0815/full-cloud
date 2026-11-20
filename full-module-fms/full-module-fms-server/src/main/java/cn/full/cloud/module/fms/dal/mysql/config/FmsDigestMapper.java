package cn.full.cloud.module.fms.dal.mysql.config;

import cn.full.cloud.framework.mybatis.core.mapper.BaseMapperX;
import cn.full.cloud.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.full.cloud.module.fms.dal.dataobject.config.FmsDigestDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

/**
 * FMS 常用摘要 Mapper
 *
 * @author 芋道源码
 */
@Mapper
public interface FmsDigestMapper extends BaseMapperX<FmsDigestDO> {

    default List<FmsDigestDO> selectListByAccountSetId(Long accountSetId) {
        return selectList(new LambdaQueryWrapperX<FmsDigestDO>()
                .eq(FmsDigestDO::getAccountSetId, accountSetId)
                .orderByDesc(FmsDigestDO::getUpdateTime)
                .orderByDesc(FmsDigestDO::getId));
    }

}
